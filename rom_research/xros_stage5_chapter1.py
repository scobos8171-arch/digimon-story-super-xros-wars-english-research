"""Translate the next contiguous Xros Wars story block into English."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from rom_research.nds_inventory import read_header, read_nitrofs
from rom_research.nitrofs_patch import replace_nitrofs_files
from rom_research.story_messages import build_message_table, parse_message_table
from rom_research.xros_pak import (
    XrosPak,
    build_xros_pak,
    find_nitro_file,
    read_nitro_file,
)


ARCHIVE = "MSG/MESPAK02.PAK"
ENTRY = 1

CHAPTER = [
    "And now Nene is\nacting strangely too.",
    "Nene Amano is a mysterious girl\nwith many secrets.\nJust when we thought\nshe had joined us,\nshe disappeared once,\nand has acted strangely\nsince returning.",
    "Zenjiro was acting\npretty strange too.",
    "He has been strange\nfrom the beginning!",
    "They are talking about you.\nDid you hear that, Zenjiro?",
    "Now enjoy our adventure\nin the mysterious\nL-Esta Zone!",
    "Squishy Digimon,\nsquishy Digimon!",
    "You are the squishy Digimon!\nI told you, I am a Weapon Digimon!\nWea-pon Di-gi-mon!",
    "Squishy, squishy!",
    "Hey! We found Starmon\nand the Pickmons!",
    "What were you doing here?\nWe searched everywhere!",
    "...Taiki,\nare these the only ones?\nWhere are Nene,\nSparrowmon, and the others?",
    "Nene wandered off\nand has not returned.\nShe never said where she went,\nand we cannot contact her.",
    "They can look after themselves.\nI am sure they will\nwander back eventually.",
    "Hey! Wait up!",
    "That was awful!\nWhy did you leave me behind?\nWhat if I got lost\nin this overgrown jungle?",
    "Sorry, Akari...\n\nWe were worried about\nthe Pickmons and hurried ahead.",
    "Ballistamon and I\nkept an eye on you!\nWe made sure you\ndid not get lost.",
    "Ballistamon heard Akari\npanting behind us.\nI knew she was following!",
    "If you knew I was exhausted,\nyou could have helped me!",
    "Easy, everyone.\nMore importantly,\nlook what we found!",
    "See? Amazing, right?",
    "Right!",
    "It is impressive,\nbut what is it?",
    "A Weapon Digimon!\n\nEven I have never seen\na real one before.\nThey are Digimon that can\ntransform into weapons,\nand this is one of the oldest,\nstrongest, largest,\nand rarest types.",
    "A rare type!",
    "That is a Digimon?\nIt is not moving at all.",
    "When Weapon Digimon\nexhaust all their power,\nthey return to weapon form\nand enter a long sleep.",
    "When will it wake up?",
    "Nobody knows.\nProbably far in the future.\nNo Weapon Digimon like this\nhas ever awakened.",
    "Wait. You said\n'a long sleep' so casually.\nDo you mean the peaceful,\nforever kind of sleep?",
    "What is that sound?",
    "...Taiki?\nWhat is wrong?",
    "I have to save them...\nI have to...",
    "What was that?\nWho am I supposed to save?",
    "Taiki, are you okay?",
    "...Huh? What do you mean?",
    "You froze and stared ahead.\nYou did not move,\nand you did not respond.\nAre you feeling sick?",
    "I am fine physically.\nI suddenly heard\nsomeone's voice.",
    "Like when you first\nmet Shoutmon?",
    "...Yes, it was similar.\n\nBut this voice was distant\nand disappeared quickly.\nI had no chance to answer.",
    "Then someone is asking\nTaiki for help!\nLet us split up\nand find them!",
    "Hold it right there!",
    "Splitting up is fine,\nbut have you forgotten\nsomething important?",
    "Your innocent hearts\nfrom long ago?",
    "No!\n\nYou were about to abandon\nthe Cross Heart mood-maker!",
    "...Cutemon is with\nDorulumon, right?",
    "No, no, enough jokes!\nDo not tell me you forgot\nyour friend Zenjiro!",
    "Dorulumon, poor Zenjiro...\nJust as I expected,\neveryone forgot him...",
    "If we had not found him\nwhile passing by,\nhe would have been abandoned\nin the jungle.\nYou might never\nhave remembered him.",
    "Shh!\n\nDo not say that so loudly!\nZenjiro is sensitive\nabout being forgettable.\nHe will be crushed!",
    "Wait, pink Digimon.\nYou are louder than anyone,\nand those comments hurt!\nYou are making me want\nto sit down and cry!",
    "W-What...?\nHuh?",
    "What!?",
    "Zenjiro disappeared!\nWas it because I told\nthe truth?",
    "If he could vanish\nfrom something like that,\nit would be impressive.\nNot a bad reaction for him.",
    "This is no time\nto be so calm!\nWhat just happened?\nWhere did Zenjiro go?\nTaiki, did he enter\nthe Xros Loader?",
    "He is human, so he cannot\nenter the Xros Loader.\nIt looked like he was\ntransported somewhere.",
    "S-Somewhere?\nDo you know where?",
    "Ahh! Dorulumon\nand the others too!",
    "Be careful, Taiki.\nSomething is wrong.\nThe zone boundary is shaking,\nand space is warping.\nAn incredible force\nis pulling us somewhere!",
    "Why pull us in?\nWho would do this,\nand for what reason?",
    "Maybe it is the person\nwhose voice Taiki heard.",
    "Logically,\nthere is no other answer.",
    "B-Ballistamon too!",
    "Oh no...\nEven the Starmons...",
    "If that person did this,\nare they trying to summon us?\nThey could simply ask for help.\nThe voice did not sound\nlike someone evil.",
    "How can you be so relaxed?\nWe do not know who they are\nor what they want!\nSomeone causing this chaos\ncannot be harmless!",
    "Okay, I understand.\nThen let us go.",
    "They want something from us.\nIf we meet them,\nwe will learn who they are\nand what they want!",
    "...You are right.\nWe cannot escape,\nand Ballistamon and the others\nalready went ahead.\nFine! Let us charge in!",
    "I have to save them...\n\nI have to save everyone...",
    "You are awake, Taiki.",
    "That voice...",
    "...Voice?\nI did not hear anything.",
    "Look around, Taiki.\nWe definitely reached\nanother zone,\nbut I have never been\ntransported like that before.",
    "Another zone...?",
    "Where is Akari?\nZenjiro is missing too!",
    "Everyone was separated.\nI hope this zone is safe...",
    "There are no nearby signals\nfrom humans or Digimon.\nFirst, we must find\nAkari and the others.",
]


def build(source: Path, output: Path, manifest: Path) -> dict[str, object]:
    with source.open("rb") as handle:
        header = read_header(handle)
        files = read_nitrofs(handle, header)
        pak = XrosPak.from_bytes(
            read_nitro_file(handle, find_nitro_file(files, ARCHIVE))
        )
    entries = [pak.unpacked_data(index) for index in range(len(pak.entries))]
    original = entries[ENTRY]
    _offsets, strings = parse_message_table(original, encoding="shift_jis")
    patched = list(strings)
    for index, text in enumerate(CHAPTER):
        patched[index] = text.encode("cp1252")
    entries[ENTRY] = build_message_table(original, patched)
    replacement = build_xros_pak(entries)
    rom = replace_nitrofs_files(source.read_bytes(), {ARCHIVE: replacement})
    output.write_bytes(rom)

    with output.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        checked_pak = XrosPak.from_bytes(
            read_nitro_file(handle, find_nitro_file(files, ARCHIVE))
        )
    _checked_offsets, checked = parse_message_table(
        checked_pak.unpacked_data(ENTRY), encoding="shift_jis"
    )
    for index, text in enumerate(CHAPTER):
        if checked[index] != text.encode("cp1252"):
            raise AssertionError(f"Verification failed at chapter string {index}")

    result = {
        "source_rom": str(source),
        "output_rom": str(output),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "output_sha256": hashlib.sha256(rom).hexdigest(),
        "archive": ARCHIVE,
        "entry": ENTRY,
        "translated_strings_this_stage": len(CHAPTER),
        "translated_story_strings_total": 160,
        "scope": "Jungle reunion through dimensional transfer and arrival in the next zone.",
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
    print(
        f"Built {args.output} with {result['translated_strings_this_stage']} "
        f"additional story strings; SHA-256 {result['output_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
