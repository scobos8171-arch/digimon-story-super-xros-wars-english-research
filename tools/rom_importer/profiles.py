from __future__ import annotations

import re
import struct
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path

from .archives import XrosPak
from .nds import NdsRom


@dataclass(frozen=True)
class SpeciesRecord:
    source_game: str
    internal_id: int
    display_name: str
    original_name: str
    battle_entry: int
    battle_format: str
    walk_entry: int | None = None
    portrait_entry: int | None = None
    full_body_entry: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RomProfile:
    key: str
    title: str
    game_codes: tuple[str, ...]
    name_first: int
    name_last: int
    battle_first: int


LOST_PROFILE = RomProfile(
    key="lost_evolution",
    title="Digimon Story: Lost Evolution",
    game_codes=("BLEJ",),
    name_first=119,
    name_last=440,
    # The species bank starts at 1038.  1061 was the first rookie-looking
    # resource and caused every compact name-table slot after Chicchimon to
    # be paired with artwork 23 entries late.
    battle_first=1038,
)
XROS_RED_PROFILE = RomProfile(
    key="xros_red",
    title="Digimon Story: Super Xros Wars Red",
    game_codes=("TLTJ",),
    name_first=651,
    name_last=1048,
    battle_first=903,
)
XROS_BLUE_PROFILE = RomProfile(
    key="xros_blue",
    title="Digimon Story: Super Xros Wars Blue",
    game_codes=("TBFJ",),
    name_first=651,
    name_last=1048,
    battle_first=903,
)
MESSAGE_PROFILES = (LOST_PROFILE, XROS_RED_PROFILE, XROS_BLUE_PROFILE)


def detect_profile(rom: NdsRom) -> str:
    if rom.header.game_code == "A6RE":
        return "dusk"
    for profile in MESSAGE_PROFILES:
        if rom.header.game_code in profile.game_codes:
            return profile.key
    raise ValueError(
        f"Unsupported ROM {rom.header.title!r} ({rom.header.game_code}); "
        "expected Dusk US, Lost Evolution, or Xros Wars Red/Blue"
    )


_DUSK_SYMBOLS = {
    0x0000: " ",
    0x000B: "/",
    0x000C: "%",
    0x000D: ":",
    0x000E: "'",
    0x000F: '"',
    0x0010: "·",
    0x0011: ",",
    0x0012: ".",
    0x0013: "!",
    0x0014: "?",
    0x0015: "(",
    0x0016: ")",
    0x0017: "+",
    0x0018: "-",
    0x0019: "=",
    0x0054: "*",
    0x0055: "×",
    0x005B: "&",
}


def decode_dusk_word(value: int) -> str:
    if 0x0001 <= value <= 0x000A:
        return chr(ord("0") + value - 1)
    if 0x0020 <= value <= 0x0039:
        return chr(ord("A") + value - 0x20)
    if 0x003A <= value <= 0x0053:
        return chr(ord("a") + value - 0x3A)
    return _DUSK_SYMBOLS.get(value, f"{{{value:04X}}}")


def parse_dusk_strings(data: bytes) -> tuple[str, ...]:
    strings: list[str] = []
    current: list[str] = []
    cursor = 0
    while cursor + 1 < len(data):
        value = struct.unpack_from("<H", data, cursor)[0]
        cursor += 2
        if value in {0xFFFE, 0xFFFF}:
            strings.append("".join(current))
            current = []
        else:
            current.append(decode_dusk_word(value))
    if current:
        strings.append("".join(current))
    return tuple(strings)


def dusk_species(rom: NdsRom) -> tuple[SpeciesRecord, ...]:
    # These are fixed ARM9 regions in the US Dusk cartridge build.
    name_start, name_end = 0x0010B6C2, 0x0010D978
    sprite_start, sprite_end = 0x000FCE04, 0x00100834
    names = parse_dusk_strings(rom.read_range(name_start, name_end - name_start))
    expected = 435
    if len(names) < expected:
        raise ValueError(f"Dusk name table has only {len(names)} of {expected} names")
    sprite_data = rom.read_range(sprite_start, sprite_end - sprite_start + 0x10)
    records: list[SpeciesRecord] = []
    id_base = 65
    for name_index, name in enumerate(names[:expected]):
        internal_id = id_base + name_index
        cursor = internal_id * 0x10
        if cursor + 0x10 > len(sprite_data):
            raise ValueError(f"Dusk sprite map is missing ID {internal_id}")
        record_id, walk_entry, battle_entry, packed_upper = struct.unpack_from(
            "<IIII", sprite_data, cursor
        )
        if record_id != internal_id:
            raise ValueError(
                f"Dusk sprite map ID mismatch at {internal_id}: {record_id}"
            )
        records.append(
            SpeciesRecord(
                source_game="dusk",
                internal_id=internal_id,
                display_name=name,
                original_name=name,
                battle_entry=battle_entry,
                battle_format="dusk_group",
                walk_entry=walk_entry,
                portrait_entry=packed_upper & 0xFFFF,
                full_body_entry=(packed_upper >> 16) & 0xFFFF,
            )
        )
    return tuple(records)


def parse_message_table(data: bytes) -> tuple[bytes, ...]:
    if len(data) < 8:
        raise ValueError("Message table header is truncated")
    count = struct.unpack_from("<I", data, 4)[0]
    table_end = 8 + count * 4
    if count > 100_000 or table_end > len(data):
        raise ValueError("Invalid message pointer table")
    offsets = struct.unpack_from(f"<{count}I", data, 8) if count else ()
    strings: list[bytes] = []
    for index, offset in enumerate(offsets):
        next_offset = offsets[index + 1] if index + 1 < len(offsets) else len(data)
        if offset < table_end or next_offset < offset or next_offset > len(data):
            raise ValueError(f"Invalid message range at string {index}")
        strings.append(data[offset:next_offset].rstrip(b"\0"))
    return tuple(strings)


def decode_message_name(raw: bytes) -> str:
    for encoding in ("utf-8", "shift_jis", "cp932"):
        try:
            text = raw.decode(encoding)
            if "�" not in text:
                return text.strip()
        except UnicodeDecodeError:
            continue
    return raw.decode("shift_jis", errors="replace").strip()


def message_species(rom: NdsRom, profile: RomProfile) -> tuple[SpeciesRecord, ...]:
    archive = XrosPak(rom.read("MSG/MESPAK00.PAK"))
    names = parse_message_table(archive.unpack(0))
    if profile.name_last >= len(names):
        raise ValueError(
            f"{profile.title} name table ends at {len(names) - 1}, "
            f"expected {profile.name_last}"
        )
    records: list[SpeciesRecord] = []
    for string_index in range(profile.name_first, profile.name_last + 1):
        internal_id = string_index - profile.name_first
        original_name = decode_message_name(names[string_index])
        # The localized Xros build uses full-width Latin glyphs so it remains
        # compatible with the original Japanese font renderer.  Normalize the
        # exported display name while preserving the exact source spelling.
        name = unicodedata.normalize("NFKC", original_name)
        if profile.key in {"xros_blue", "xros_red"}:
            name = {
                367: "Greymon (Blue)",
                384: "Greymon (Orange)",
            }.get(internal_id, name)
        battle_entry = profile.battle_first + internal_id
        # Lost Evolution inserts a non-roster coordinated resource immediately
        # before Susanoomon.  The compact message table does not include it.
        if profile.key == "lost_evolution" and internal_id >= 299:
            battle_entry += 1
        # Xros' last bank is not in message-table order: three unused/alternate
        # banks sit around Shoutmon x3, Spadamon and Shoutmon (Kuro), then the
        # final boss/special-form run resumes four slots later.
        if profile.key in {"xros_blue", "xros_red"}:
            if internal_id == 382:  # Spadamon
                battle_entry = 1287
            elif internal_id == 383:  # Shoutmon (Kuro)
                battle_entry = 1286
            elif internal_id >= 384:
                battle_entry = internal_id + 907
        records.append(
            SpeciesRecord(
                source_game=profile.key,
                internal_id=internal_id,
                display_name=name,
                original_name=original_name,
                battle_entry=battle_entry,
                battle_format="coordinated",
            )
        )
    return tuple(records)


def species_for_rom(rom: NdsRom) -> tuple[SpeciesRecord, ...]:
    profile = detect_profile(rom)
    if profile == "dusk":
        return dusk_species(rom)
    message_profile = next(item for item in MESSAGE_PROFILES if item.key == profile)
    return message_species(rom, message_profile)


NAME_ALIASES = {
    # Cross-game localization/truncation variants that refer to one species.
    "dracmon": "dracumon",
    "dracumon": "dracumon",
    "dfalcomon": "dotfalcomon",
    "dotfalcomon": "dotfalcomon",
    "penmon": "penguinmon",
    "shakomon": "syakomon",
    "yukiagumon": "snowagumon",
    "ganimon": "crabmon",
    "pawnchessmonshiro": "pawnchessmonwhite",
    "mechanolimon": "mekanorimon",
    "tyranomon": "tyrannomon",
    "vegiemon": "veggiemon",
    "kyuubimon": "kyubimon",
    "chrysalimon": "kurisarimon",
    "seasalmon": "seasarmon",
    "evilmon": "vilemon",
    "raptordramon": "reptiledramon",
    "hanumon": "apemon",
    "starmonlegend": "starmon",
    "darktyranomon": "dktyrannomon",
    "darktyrannomon": "dktyrannomon",
    "minotarmon": "minotarumon",
    "diatrimon": "diatrymon",
    "dorimogemon": "drimogemon",
    "tsuchidarmon": "tsuchidarumon",
    "lukamon": "dolphmon",
    "centalmon": "centarumon",
    "nightchessmonshiro": "knightchessmonwhite",
    "volcamon": "volcanomon",
    "metalgreymonlegend": "metalgreymon",
    "mammon": "mammothmon",
    "tonosamagekomon": "shogungekomon",
    "tonosamaagekomon": "shogungekomon",
    "tilomon": "tylomon",
    "weregarurumonb": "wargarurumonblack",
    "weregarurumon": "wargarurumonblue",
    "nanomonlegend": "datamon",
    "cyberdramonlegend": "cyberdramon",
    "sindooramon": "sinduramon",
    "hangyomon": "divermon",
    "whyemonkanzentai": "whamonultimate",
    "insekimon": "meteormon",
    "rizegreymon": "risegreymon",
    "garbemon": "garbagemon",
    "lucemonfm": "lucemonchaosmode",
    "mametyranomon": "mametyramon",
    "mametiramon": "mametyramon",
    "metyranomon": "metaltyrannomon",
    "extyranomon": "extyrannomon",
    "lynxmon": "lanksmon",
    "shawjamon": "shaujinmon",
    "bishopchesmon": "bishopchessmon",
    "hkabuterimon": "herculeskabuterimon",
    "demon": "creepymon",
    "griphomon": "gryphonmon",
    "plesiomon": "preciomon",
    "slashangemon": "slangemon",
    "beelzebumonlegend": "beelzemon",
    "bancholeomon": "bantyoleomon",
    "mesedramon": "metalseadramon",
    "meseadramon": "metalseadramon",
    "skullmammon": "skullmammothmon",
    "gkuwagamon": "grandiskuwagamon",
    "grankuwagamon": "grandiskuwagamon",
    "millenniumon": "millenniummon",
    "mrgaogamon": "miragegaogamon",
    "chronomonhm": "chronomonholymode",
    "lilithmonlegend": "lilithmon",
    "mgaogamonbm": "miragegaogamonburstmode",
    "beelzemonbm": "beelzemonblastmode",
    "argomonm": "argomonmega",
    "mtyrannomon": "mastertyrannomon",
    "airismon": "ancientirismon",
    "agarurumon": "ancientgarurumon",
    "amtheriumon": "ancientmegatheriumon",
    "agreymon": "ancientgreymon",
    "amermaidmon": "ancientmermaidmon",
    "awisemon": "ancientwisemon",
    "asphinxmon": "ancientsphinxmon",
    "atroiamon": "ancienttroiamon",
    "abeatmon": "ancientbeatmon",
    "avolcamon": "ancientvolcamon",
    "ufveedramon": "ulforceveedramon",
    "tgvespamon": "tigervespamon",
    "ipdramonpm": "imperialdramonpaladinmode",
    "ipdramonfm": "imperialdramonfightermode",
    "ipdramondm": "imperialdramondragonmode",
    "imperialdramon": "imperialdramonfightermode",
    "mmillenniummon": "moonmillenniumon",
    "sgreymonbm": "shinegreymonburstmode",
    "shinegreymonbm": "shinegreymonburstmode",
    "sgreymonrm": "shinegreymonruinmode",
    "ravemonbm": "ravemonburstmode",
    "rosemonbm": "rosemonburstmode",
    "saintgargomon": "megagargomon",
    "kentaurosmon": "sleipmon",
    "sngreymon": "shinegreymon",
    "bwargreymon": "blackwargreymon",
    "cherubimone": "cherubimonevil",
    "cherubimong": "cherubimongood",
    "belialvamdemon": "malomyotismon",
    "gallantmoncm": "gallantmoncrimsonmode",
    "cgallantmon": "chaosgallantmon",
    "highandromon": "hiandromon",
    "marinangemon": "marineangemon",
    "dmgaogamon": "dotmiragegaogamon",
    "dsgreymon": "dotshinegreymon",
    "leopardmon": "duftmon",
    "neptunmon": "neptunemon",
    "vnmyotismon": "venommyotismon",
    "mmyotismon": "malomyotismon",
    "zdmillenniummon": "zeedmillenniummon",
    "zeedmillenniumon": "zeedmillenniummon",
    "exeraser": "exeraseromega",
    "exeraserω": "exeraseromega",
}

CANONICAL_DISPLAY_NAMES = {
    "dracumon": "Dracumon",
    "dotfalcomon": "DotFalcomon",
    "volcanomon": "Volcanomon",
    "wargarurumonblack": "WarGarurumon (Black)",
    "wargarurumonblue": "WarGarurumon (Blue)",
    "whamonultimate": "Whamon (Ultimate)",
    "blackwargreymon": "BlackWarGreymon",
    "cherubimonevil": "Cherubimon (Evil)",
    "cherubimongood": "Cherubimon (Good)",
    "malomyotismon": "MaloMyotismon",
    "gallantmoncrimsonmode": "Gallantmon Crimson Mode",
    "chaosgallantmon": "Chaos Gallantmon",
    "imperialdramondragonmode": "Imperialdramon Dragon Mode",
    "imperialdramonfightermode": "Imperialdramon Fighter Mode",
    "imperialdramonpaladinmode": "Imperialdramon Paladin Mode",
    "hiandromon": "HiAndromon",
    "marineangemon": "MarineAngemon",
    "dotmiragegaogamon": "DotMirageGaogamon",
    "dotshinegreymon": "DotShineGreymon",
    "duftmon": "Duftmon",
    "neptunemon": "Neptunemon",
    "shinegreymonburstmode": "ShineGreymon Burst Mode",
    "shinegreymonruinmode": "ShineGreymon Ruin Mode",
    "ravemonburstmode": "Ravemon Burst Mode",
    "rosemonburstmode": "Rosemon Burst Mode",
    "megagargomon": "MegaGargomon",
    "sleipmon": "Sleipmon",
    "shinegreymon": "ShineGreymon",
    "venommyotismon": "VenomMyotismon",
    "zeedmillenniummon": "ZeedMillenniummon",
    "exeraseromega": "EXEraser Ω",
}


def normalize_name(name: str) -> str:
    normalized = unicodedata.normalize("NFKC", name).casefold()
    normalized = normalized.replace("？", "?")
    normalized = "".join(character for character in normalized if character.isalnum())
    return NAME_ALIASES.get(normalized, normalized)


def canonical_display_name(name: str) -> str:
    return CANONICAL_DISPLAY_NAMES.get(normalize_name(name), name)


def safe_slug(name: str, fallback: str) -> str:
    normalized = unicodedata.normalize("NFKD", name)
    ascii_name = normalized.encode("ascii", errors="ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", ascii_name).strip("_").lower()
    return slug or fallback


def discover_roms(directory: Path) -> tuple[Path, ...]:
    directory = Path(directory)
    if not directory.exists():
        return ()
    return tuple(sorted(directory.glob("*.nds")))
