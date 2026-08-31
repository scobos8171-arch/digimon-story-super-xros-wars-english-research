"""GPU-assisted search for damage-formula hypotheses.

This deliberately tests a hypothesis family; it does not claim that the best
fit is cartridge-authentic. Assembly-derived constants and new runtime trials
should progressively narrow or replace the searched parameters.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import torch


ATTACK_WEIGHTS = torch.tensor([[1.0, 0.0], [0.3, 0.7], [0.65, 0.35]])
DEFENSE_WEIGHTS = torch.tensor([[1.0, 0.0], [0.4, 0.6], [0.7, 0.3]])


def trial_tensors(document: dict, device: torch.device) -> dict[str, torch.Tensor]:
    rows = document["trials"]
    classes = torch.tensor([row["damage_class"] for row in rows], device=device, dtype=torch.long)
    aw = ATTACK_WEIGHTS.to(device)[classes]
    dw = DEFENSE_WEIGHTS.to(device)[classes]
    attacker_pair = torch.tensor(
        [[row["attacker"]["primary_attack"], row["attacker"]["secondary_stat"]] for row in rows],
        device=device,
    )
    defender_pair = torch.tensor(
        [[row["defender"]["primary_defense"], row["defender"]["secondary_stat"]] for row in rows],
        device=device,
    )
    return {
        "attack": (attacker_pair * aw).sum(dim=1),
        "defense": (defender_pair * dw).sum(dim=1),
        "power": torch.tensor([row["effect_power_parameter"] for row in rows], device=device),
        "attacker_level": torch.tensor([row["attacker"]["level"] for row in rows], device=device),
        "defender_level": torch.tensor([row["defender"]["level"] for row in rows], device=device),
        "effectiveness": torch.tensor([row["effectiveness_multiplier"] for row in rows], device=device),
        "observed": torch.tensor([row["observed_damage"] for row in rows], device=device),
    }


def search(
    document: dict,
    *,
    candidates: int,
    batch_size: int,
    seed: int,
    device: torch.device,
    duration_seconds: float = 0.0,
) -> dict:
    data = trial_tensors(document, device)
    generator = torch.Generator(device=device).manual_seed(seed)
    best_error = float("inf")
    best = None
    tested = 0
    started = time.perf_counter()

    next_progress = 10.0
    while tested < candidates:
        if duration_seconds > 0 and tested > 0 and time.perf_counter() - started >= duration_seconds:
            break
        count = min(batch_size, candidates - tested)
        # Candidate family:
        # floor(max(1, ((A*(P/div+bias) - D*dscale + L*lscale + offset)
        #              * postscale * effectiveness)))
        params = torch.rand((count, 6), generator=generator, device=device)
        power_divisor = 50.0 + params[:, 0] * 450.0
        power_bias = params[:, 1] * 2.0
        defense_scale = params[:, 2] * 2.0
        level_scale = params[:, 3] * 3.0
        offset = -50.0 + params[:, 4] * 100.0
        post_scale = 0.05 + params[:, 5] * 1.95

        predicted_float = (
            data["attack"][None, :] * (data["power"][None, :] / power_divisor[:, None] + power_bias[:, None])
            - data["defense"][None, :] * defense_scale[:, None]
            + data["attacker_level"][None, :] * level_scale[:, None]
            + offset[:, None]
        ) * post_scale[:, None] * data["effectiveness"][None, :]
        predicted = torch.floor(torch.clamp(predicted_float, min=1.0))
        errors = torch.abs(predicted - data["observed"][None, :]).sum(dim=1)
        value, index = torch.min(errors, dim=0)
        if value.item() < best_error:
            i = int(index.item())
            best_error = float(value.item())
            best = {
                "absolute_error": best_error,
                "power_divisor": float(power_divisor[i].item()),
                "power_bias": float(power_bias[i].item()),
                "defense_scale": float(defense_scale[i].item()),
                "level_scale": float(level_scale[i].item()),
                "offset": float(offset[i].item()),
                "post_scale": float(post_scale[i].item()),
                "predicted": [int(value) for value in predicted[i].tolist()],
            }
        tested += count

        # CUDA work is asynchronous. Timed runs must synchronize so elapsed
        # wall-clock time represents completed calculations rather than queued
        # kernels. It also makes progress reports honest.
        if duration_seconds > 0:
            torch.cuda.synchronize() if device.type == "cuda" else None
            elapsed_now = time.perf_counter() - started
            if elapsed_now >= next_progress:
                print(
                    f"progress: {elapsed_now:8.1f}s, {tested:,} candidates, "
                    f"best error {best_error:g}",
                    flush=True,
                )
                next_progress += 10.0

    torch.cuda.synchronize() if device.type == "cuda" else None
    elapsed = time.perf_counter() - started
    return {
        "device": str(device),
        "gpu_name": torch.cuda.get_device_name(device) if device.type == "cuda" else None,
        "candidate_formula_family": "documented in gpu_formula_search.py; hypothesis only",
        "candidates_tested": tested,
        "requested_duration_seconds": duration_seconds or None,
        "elapsed_seconds": elapsed,
        "candidates_per_second": tested / elapsed,
        "best": best,
        "exact_fit_found": bool(best and best["absolute_error"] == 0),
        "warning": "A numerical fit is not proof. Accept a formula only after its operations/constants match ARM code.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixtures", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--candidates", type=int, default=5_000_000)
    parser.add_argument("--batch-size", type=int, default=250_000)
    parser.add_argument("--seed", type=int, default=0x58524F53)
    parser.add_argument(
        "--duration-seconds",
        type=float,
        default=0.0,
        help="run for at least this many wall-clock seconds; 0 uses only --candidates",
    )
    parser.add_argument("--cpu", action="store_true")
    args = parser.parse_args()
    device = torch.device("cpu" if args.cpu or not torch.cuda.is_available() else "cuda")
    document = json.loads(args.fixtures.read_text(encoding="utf-8"))
    candidate_limit = args.candidates if args.duration_seconds <= 0 else 2**63 - 1
    report = search(
        document,
        candidates=candidate_limit,
        batch_size=args.batch_size,
        seed=args.seed,
        device=device,
        duration_seconds=args.duration_seconds,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
