"""Build Stage 4 with a coherent English opening and battle tutorial."""

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
ENTRY = 0

OPENING = [
    "Hey, everyone! Nice to meet you!\n\nThanks for starting\nDigimon Battle Chronicle!",
    "The anime has not even started,\nand you are already here!\nNow those are loyal fans!",
    "Before we begin,\nlet us introduce the team!",
    "First, me: Taiki Kudo.\nI am the hero of\nDigimon Xros Wars!\nWhenever someone needs help,\nI cannot ignore them.\nThat is how I get dragged\ninto adventures like this.",
    "My powerful manager is\nmy childhood friend,\nAkari Hinomoto.",
    "And this needlessly fiery guy\nis Zenjiro Tsurugi.\n\nI do not remember agreeing,\nbut he calls himself\nmy eternal rival.",
    "Leave the Digimon introductions\nto me!\nI am the future Digimon King,\nTaiki's partner, Shoutmon!\nI will rock Xros Wars too!",
    "For better or worse,\nhe always charges straight ahead.",
    "Big, tough, and dependable:\nBallistamon!",
    "Quiet, calm,\nand reliable as a samurai.",
    "Sarcastic, careless,\nand too cool for rules:\nDorulumon!",
    "He is a free spirit\nwho answers to nobody.",
    "Small, loud, and numerous:\nthe Starmons!",
    "Together they become\nthe mighty Star Sword!",
    "A voice calling for help\nled us to a strange island\nfloating in the sky:\nL-Esta Zone!",
    "The island was not\nthe only strange thing there.",
    "There was Sky Fort,\na mobile fortress;\nSpadamon, the zone's guardian;\na Fusion System able to create\nnew Digimon;\nand an enemy army\ntrying to seize it all...",
    "And Taiki's rival\nwas acting suspiciously too.",
    "The cool and mysterious\nKiriha Aonuma,\nand the equally mysterious\nNene Amano.\nYour version decides\nwhich one you confront!\nBlue Flare reveals\nKiriha's secrets;\nTwilight reveals Nene's!",
    "Wait. Was Zenjiro not\nsupposed to be your rival too?",
    "No. He was captured\nalong with the rest of us.",
    "Besides, nobody would buy\na Zenjiro version!",
    "Now our adventure begins\nin the mysterious\nL-Esta Zone!",
    "Taiki!\nTaiki, wake up!",
    "Oh, good.\nEveryone is safe.\nI dreamed Akari was captured\nby some bad guys.",
    "Stop talking in your sleep!\nWe are not safe at all!\nAll of us were captured!\nDo you remember arriving here?\nWe found the Digimon\nwho called for help...\nthen the enemy shocked us\nand knocked us unconscious.",
    "...Then where are Shoutmon\nand the others?\nDo you think they...",
    "They were taken away\nwhile we were unconscious.\nWhat do we do now, Taiki?",
    "What else?\nWe rescue them!",
    "That is always your answer.\nRescue this, rescue that...\nRight now, we are the ones\nwho need rescuing!",
    "The voice we heard\nsaid the same thing:\n'I have to save everyone.'\nIt felt too familiar.\nI could not ignore it.",
    "Hey! Sorry to keep you waiting!",
    "Ahhh!\nYou are the Digimon from before!",
    "The one who asked us\nfor help!",
    "Shh! Keep quiet!\n\nFollow me before they find us!",
    "W-Wait!\nWhy are you here?",
    "You came to rescue us, right?\nThen rescuing you is natural!\nI am Spadamon.\nThank you for coming.",
    "We should thank you.\nI am Taiki Kudo.\nThese are Akari and Zenjiro.",
    "...Someone is coming!\nDo not move!",
    "Hey, prisoners!\nI brought your friends!",
    "Those idiots built\nsuch a complicated door.\nNo matter what I try,\nI cannot open it.\nThat makes me the only one\nwho can bring prisoners in!",
    "Shoutmon! Are you okay?",
    "You probably cannot escape,\nbut listen carefully!\nDo not try anything funny!\nWe still have your friends,\nand they will pay for it!",
    "Shoutmon!\nAre you all right?",
    "Come on, wake up!\nShoutmon!",
    "Shoutmon!!",
    "...Taiki!\nThis is bad!\nSparrowmon and the others\nwere taken somewhere else!\nThose creeps are planning\nsomething strange!",
    "...What!?",
    "Huh? You are the Digimon\nwho called us here.\nI thought you escaped.",
    "I did escape.\nMy friends helped me,\njust like every time before.\n...Taiki,\nI need to ask a favor.",
    "I want to rescue every captive:\nmy friends and yours.\nSo please,\nwill you lend me your strength?",
    "Of course!",
    "That is what I wanted to hear!",
    "First we need to find\na way through this door.",
    "That part is easy,\nif you do not mind being seen.\nBefore the invasion army\nstole this place,\nit belonged to us.",
    "All right, Taiki!\nLet us smash those guys!",
    "We heard this zone\nwas hiding something.\nWhat is it?\nTell us now!",
    "I-I do not know!\nA low-ranking Digimon like me\nwould never be told!",
    "Then you are useless!\nI will throw you outside\nand see whether you can fly!",
    "Stop!",
    "D-Do not touch my friends!\nI will not forgive you!",
    "Hah! Your voice is shaking.\nSo you are the coward\nwho survived?",
    "You ran while your friends\nwere attacked.\nWill you use these people\nas shields this time?",
    "I will not run again,\nand I will not sacrifice anyone!\nI will defeat you\nand rescue everyone!\nTaiki, Shoutmon,\nplease fight with me!",
    "Leave it to us, Spadamon!\nTaiki is our General.\nNobody commands Digimon\nbetter than him!\nRight, Taiki?",
    "A General's commands\ncan decide a Digimon's fate!\nUse the lower screen\nto command your team!",
    "Commands use the Command Ring.\nPress Left or Right\nto rotate it.\nPress the A Button\nto choose a command!",
    "Choose FIGHT for a technique\nthat does not consume MP.\nUse it when you want\nto conserve MP!",
    "0000000000\n0000000000",
    "Choose DIGIXROS\nto combine Digimon!\n\nYou must first learn\na Fusion Technique,\nthen place every required\nDigimon in your party.",
    "Choose ITEM to use\na consumable item.\nItems can cure status effects,\nrestore HP or MP,\nand revive fallen Digimon!",
    "Choose TACTICS\nto enable Auto Battle.\nFull Power uses the strongest\nmove that can defeat a target.\nConserve selects low-MP moves.\nGuard focuses on defense.\nEscape makes Digimon flee.\nIf even one escapes,\nthe battle can be avoided!",
    "Choose FORMATION\nto exchange the selected Digimon\nwith another party member!",
    "One last thing!\nPress B to redo a command.\nWhen every command is ready,\npress X to begin the turn!",
    "Would you like to hear\nthat explanation again?",
    "Explain it again.",
    "Continue to battle.",
    "All right, everyone!\nDigiXros!!",
    "We did it!",
    "You really did it!\nThat was amazing, Taiki!\nI knew I chose\nthe right General!",
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
    if len(OPENING) > len(strings):
        raise ValueError("Opening translation exceeds source string count")
    patched = list(strings)
    for index, text in enumerate(OPENING):
        patched[index] = text.encode("cp1252")
    entries[ENTRY] = build_message_table(original, patched)
    replacement = build_xros_pak(entries)
    rom = replace_nitrofs_files(source.read_bytes(), {ARCHIVE: replacement})
    output.write_bytes(rom)

    with output.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        check_pak = XrosPak.from_bytes(
            read_nitro_file(handle, find_nitro_file(files, ARCHIVE))
        )
    _check_offsets, checked = parse_message_table(
        check_pak.unpacked_data(ENTRY), encoding="shift_jis"
    )
    for index, text in enumerate(OPENING):
        if checked[index] != text.encode("cp1252"):
            raise AssertionError(f"Verification failed at opening string {index}")

    result = {
        "source_rom": str(source),
        "output_rom": str(output),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "output_sha256": hashlib.sha256(rom).hexdigest(),
        "archive": ARCHIVE,
        "entry": ENTRY,
        "translated_strings": len(OPENING),
        "scope": "English prologue, prison escape, first battle tutorial, and immediate post-battle dialogue.",
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
        f"Built {args.output} with {result['translated_strings']} opening strings; "
        f"SHA-256 {result['output_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
