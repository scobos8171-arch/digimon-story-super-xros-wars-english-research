"""Translate Xros Wars chapter-one strings 80-159."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from rom_research.nds_inventory import read_header, read_nitrofs
from rom_research.nitrofs_patch import replace_nitrofs_files
from rom_research.story_messages import build_message_table, parse_message_table
from rom_research.xros_pak import XrosPak, build_xros_pak, find_nitro_file, read_nitro_file


ARCHIVE = "MSG/MESPAK02.PAK"
ENTRY = 1
START = 80

TEXT = [
    "Right. Standing here\nwill not solve anything.\nLet us go, Taiki!",
    "You there!\nI have not seen you before!\nCome with us to Sky Fort.\nYou would not dare resist ROG,\nthe rulers of L-Esta Zone,\nwould you?",
    "ROG? Rogue?\nAs in a thief or villain?\nThat sounds openly evil!\n...\nWe did not come here willingly!\nWe were knocked around,\nthen dragged here before\nI could even complain!\nI should be asking you:\nwhat is going on!?",
    "What is going on!?",
    "What happened?",
    "What is goin' on!",
    "Enough! Be quiet!\n\nStop shouting nonsense\nall at once!",
    "Zenjiro!\nStarmon! Pickmons!",
    "Taiki Kudo! Everyone!",
    "Brothers!\nYou saved us!",
    "Hooray!\nWe are saved!",
    "That is Taiki!\nSo cool!",
    "So cooool!",
    "So you had allies.\nIt does not matter.\nROG cannot forgive resistance!\nWe will crush all of you!",
    "Taiki!",
    "All right...\nLet us go, everyone!",
    "A General's commands\ncan decide a Digimon's fate!\nUse the lower screen\nto command your team!",
    "Use the Command Ring.\nPress Left or Right\nto rotate it.\nPress A to choose a command!",
    "Choose FIGHT for a technique\nthat consumes no MP.\nUse it to conserve MP!",
    "Choose SKILL for\nspecial moves that use MP.\nSkills may hit groups\nor deal elemental damage.\nExploit an enemy weakness\nto deal double damage!",
    "Choose DIGIXROS\nto combine Digimon!\nYou must learn a Fusion Skill\nand place all required Digimon\nin your party.",
    "Choose ITEM to use supplies.\nItems cure status effects,\nrestore HP or MP,\nand revive fallen Digimon!",
    "Choose TACTICS\nfor Auto Battle.\nFull Power uses the strongest\nmove against a valid target.\nConserve uses only FIGHT.\nGuard defends completely.\nEscape attempts to flee.\nOne successful escape\nends the battle!",
    "Choose FORMATION\nto exchange the selected Digimon\nwith another party member!",
    "One last thing!\nPress B to redo commands.\nWhen ready, press X\nto begin the turn!",
    "Hear the explanation again?",
    "Explain it again.",
    "Continue to battle.",
    "All right, everyone!\nDigiXros!!",
    "Whoa!\nThank you, everyone!",
    "I knew you would\ncome rescue us!",
    "We knew it!",
    "Did we know it?",
    "We mumbled it!",
    "Who was that Digimon?\nThey called themselves ROG.",
    "They seem to be the group\ncontrolling this zone.\nROG means ROGUE,\nso I think they are\nprobably villains!",
    "Exactly, brother!\nThey are definitely evil!",
    "ROG!\nSounds villainous!",
    "We can investigate ROG later.\nZenjiro, did you see Akari?",
    "...What!?\n\nThe Pickmons were the only ones\nI found in this zone.\nWas she not with you?",
    "I see. That is worrying.\nI was transported here too.\nUntil I met the Pickmons\nfalling from the sky,\nI did not know what to do.\nI was alone, unarmed,\nand the local Digimon\nwere aggressive.",
    "Aggressive Digimon?",
    "More Digimon attack here\nthan in other zones.\nWe cannot leave\na girl alone here!",
    "You are right.\nCome on, everyone!\nLet us find Akari!",
    "Zenjiro, Starmon,\nand the Pickmons joined!",
    "Surrender peacefully?\nWhat kind of joke is that?\nWho raises a white flag\nevery time they trip?",
    "D-Dorulumon!\nThat is enough, right?\nLet us avoid a fight\nand slip away. Please?",
    "Fine by me,\nbut they want a fight.\nStand back, Cutemon.\nThis will be quick.",
    "Hand over every item\nyou collected!\nROG rules L-Esta Zone!\nI cannot believe Digimon\nstill dare oppose us!",
    "They are bluffing!\nThey will run away soon,\nif they still have tails\nwhen we finish!",
    "R-Right!\nROG's Gotsumon Squad\nwill smash them to pieces!",
    "Stop! This is dangerous!\nDo not make Dorulumon angry!",
    "...Wait a moment.\n\nYou make me sound\nlike the villain.",
    "Akari!\nDorulumon! Cutemon!",
    "Everyone!\nPerfect timing!\nPlease do something\nabout these creeps!",
    "What is wrong, Akari?\nThey do not look very dangerous.",
    "You do not understand.\nYou are the dangerous one!",
    "More enemies appeared!\nSo that explains your confidence!\nBut no matter how many come,\nROG's Gotsumon Squad\nwill never lose!",
    "We will crush all of you!",
    "Let us go, everyone!\nWe have to help Akari!",
    "Use the D-Pad\nto move the selection cursor.\nPlace it over the Digimon\nyou want to command,\nthen press A\nto open the Command Ring!",
    "If a Digimon does not need\na new command, press X.\nIts currently assigned command\nwill be executed!",
    "Hear the explanation again?",
    "Explain it again.",
    "Continue to battle.",
    "All right, everyone!\nDigiXros!!",
    "Are you okay, Akari?",
    "Ha... hahaha...\nOf course I am okay!",
    "She is smiling,\nbut her cheeks are trembling.",
    "Too many things happened\nall at once.\nI cannot decide whether\nto laugh or get angry.\nOh, I almost forgot.\nTaiki, take these.",
    "Obtained consumable items!\nBandage x3",
    "Obtained consumable items!\nEnergy Source x3",
    "They restore a Digimon's\nHP and MP.\nAt least, that is what\nthose guys said.",
    "That will help!\nNice work, Akari!",
    "...Those guys?\n\nYou mean ROG,\nthose villains?\nWhere did you get the items?",
    "Local Digimon dropped them\nwhen Dorulumon counterattacked.\n'Dropped' may be too gentle.\nThey scattered everywhere!\nEnemies kept appearing,\nand Dorulumon went wild!\nI honestly thought\nI was going to die!",
    "Use them when a Digimon\nis getting weak.\nPress START or X,\nthen choose ITEMS\nfrom the Xros Loader menu.\nDuring battle, choose ITEM\nfrom the Command Ring.",
    "Okay. I will remember.",
    "You are just ignoring\nhow much Akari suffered!?",
    "I have to save them...\nI must save L-Esta Zone\nand everyone else...\nWhatever it takes...\nNo matter what...",
]


def build(source: Path, output: Path, manifest: Path) -> dict[str, object]:
    with source.open("rb") as handle:
        header = read_header(handle)
        files = read_nitrofs(handle, header)
        pak = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, ARCHIVE)))
    entries = [pak.unpacked_data(i) for i in range(len(pak.entries))]
    original = entries[ENTRY]
    _offsets, strings = parse_message_table(original, encoding="shift_jis")
    patched = list(strings)
    for relative, text in enumerate(TEXT):
        patched[START + relative] = text.encode("cp1252")
    entries[ENTRY] = build_message_table(original, patched)
    rom = replace_nitrofs_files(source.read_bytes(), {ARCHIVE: build_xros_pak(entries)})
    output.write_bytes(rom)

    with output.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        check = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, ARCHIVE)))
    _offsets, strings = parse_message_table(check.unpacked_data(ENTRY), encoding="shift_jis")
    for relative, text in enumerate(TEXT):
        if strings[START + relative] != text.encode("cp1252"):
            raise AssertionError(f"Verification failed at {START + relative}")

    result = {
        "source_rom": str(source),
        "output_rom": str(output),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "output_sha256": hashlib.sha256(rom).hexdigest(),
        "translated_strings_this_stage": len(TEXT),
        "translated_story_strings_total": 240,
        "range": f"{ARCHIVE} entry {ENTRY}, strings {START}-{START + len(TEXT) - 1}",
        "gameplay_changes": "None",
        "movie_behavior": "Native player retained; press A/Z to skip.",
    }
    manifest.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    result = build(args.source, args.output, args.manifest)
    print(f"Built {args.output}; SHA-256 {result['output_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
