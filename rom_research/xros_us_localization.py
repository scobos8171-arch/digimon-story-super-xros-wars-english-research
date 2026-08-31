"""Apply a natural American-English editorial pass to the Xros script."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from rom_research.nds_inventory import read_header, read_nitrofs
from rom_research.nitrofs_patch import replace_nitrofs_files
from rom_research.story_messages import MESSAGE_ARCHIVES, build_message_table, parse_message_table
from rom_research.xros_pak import XrosPak, build_xros_pak, find_nitro_file, read_nitro_file


# Hand-edited scenes encountered during live testing. Coordinates are
# (MESPAK number, entry index, string index).
OVERRIDES: dict[tuple[int, int, int], str] = {
    # The Weapon Digimon/squishy exchange.
    (2, 1, 6): "Squishy Digimon!\nSquishy Digimon!",
    (2, 1, 7): (
        "You're the\nsquishy one!\nI'm a Weapon\nDigimon, got it?!\nWea-pon\nDi-gi-mon!"
    ),
    (2, 1, 8): "Squishy, squishy!",
    # Escape, regrouping, and arrival in the next Zone.
    (2, 2, 8): (
        "Hmph. I thought\nyou'd put up more\nof a fight.\nEven with a\ncheap shot, that\nwas way too easy."
    ),
    (2, 2, 9): (
        "Of all the times\nfor this to happen...\nWe need to pull\nback for now."
    ),
    (2, 2, 10): "They're gonna\ncatch me!\nS-sorry, guys!",
    (2, 2, 11): "They got away!\nYou okay with that?",
    (2, 2, 12): (
        "Hey, I can't do\neverything myself!\nWe take down the\nbig threats first.\nSpadamon can wait.\nWe've got all his\nfriends locked up.\nHe'll come running\nback for them."
    ),
    (2, 2, 13): "Take them inside\nSky Fort!",
    (2, 2, 14): "Everyone okay?!",
    (2, 2, 15): "Yeah. Nobody's\nhurt. We're good.",
    (2, 2, 16): "All right, then.\nWe did it!",
    (2, 2, 17): (
        "I have to help...\nI have to save\neveryone..."
    ),
    (2, 2, 18): "You awake, Taiki?",
    (2, 2, 19): "That voice just\nnow...",
    (2, 2, 20): "Voice? I didn't\nhear anything.",
    (2, 2, 21): (
        "Forget that,\nTaiki. Look around.\nWe're definitely\nin another Zone.\nBut I've never\nbeen thrown around\nlike that before."
    ),
    (2, 2, 22): "Another Zone...?",
    (2, 2, 23): (
        "Wait, where's\nAkari?\nZenjirou's gone,\ntoo!"
    ),
}

# Opening narration and the first prison-escape scene.
OVERRIDES.update({
    (2, 0, 0): (
        "Hey, everybody!\nNice to meet you!\n\nThanks for firing\nup this special\nDigimon preview!"
    ),
    (2, 0, 1): (
        "The anime hasn't\neven started yet,\nand you're already\nhere?\nNow that's what I\ncall dedication!"
    ),
    (2, 0, 2): (
        "Before we jump in,\nlet's meet the crew!"
    ),
    (2, 0, 3): (
        "First up, me:\nTaiki Kudo.\nI'm the hero of\nDigimon Xros Wars!\nIf somebody's in\ntrouble, I can't\njust walk away.\nThat's how I keep\ngetting dragged\ninto wild stuff."
    ),
    (2, 0, 4): (
        "Keeping me on\ntrack is my tough\nmanager--and\nchildhood friend--\nAkari Hinomoto."
    ),
    (2, 0, 5): (
        "Then there's this\npointlessly fired-up\nguy, Zenjirou\nTsurugi.\nI don't remember\nagreeing to it, but\nhe says he's my\neternal rival."
    ),
    (2, 0, 6): (
        "Leave the Digimon\nintroductions to\nme!\nI'm Shoutmon,\nfuture Digimon\nKing and Taiki's\nnumber-one partner!\nI'm gonna tear it\nup in Xros Wars!"
    ),
    (2, 0, 7): (
        "Good or bad,\nShoutmon always\ncharges straight\nahead."
    ),
    (2, 0, 8): (
        "Big, tough, and\nbuilt like a tank:\nBallistamon!"
    ),
    (2, 0, 9): (
        "He's quiet, calm,\nand dependable--\na real samurai."
    ),
    (2, 0, 10): (
        "Sarcastic, cocky,\nand way too cool\nfor anybody's\nrules: Dorulumon!"
    ),
    (2, 0, 11): (
        "He's a free spirit.\nNobody tells him\nwhat to do."
    ),
    (2, 0, 12): (
        "Tiny, noisy, and\nall over the place:\nthe Starmons!"
    ),
    (2, 0, 13): (
        "When they team up,\nthey form the mighty\nStar Sword!"
    ),
    (2, 0, 14): (
        "A desperate voice\nled us to a strange\nisland floating in\nthe sky:\nL-Esta Zone!"
    ),
    (2, 0, 15): (
        "And trust me, the\nisland wasn't the\nonly weird thing\nthere."
    ),
    (2, 0, 16): (
        "There was Sky Fort,\na mobile fortress;\nSpadamon, the Zone's\nguardian;\na Fusion System\nthat creates new\nDigimon;\nand an enemy army\ntrying to steal it\nall..."
    ),
    (2, 0, 17): (
        "Meanwhile, Taiki's\nrival was acting\npretty suspicious."
    ),
    (2, 0, 18): (
        "The cool, mysterious\nKiriha Aonuma--or\nthe equally puzzling\nNene Amano.\nYour version decides\nwho you face!\nBlue Flare reveals\nKiriha's secrets;\nTwilight uncovers\nNene's!"
    ),
    (2, 0, 19): (
        "Hold on. Wasn't\nZenjirou supposed\nto be your rival?"
    ),
    (2, 0, 20): (
        "Not this time.\nHe got captured\nwith the rest of us."
    ),
    (2, 0, 21): (
        "Besides, who'd buy\na Zenjirou version?"
    ),
    (2, 0, 22): (
        "Now let's kick off\nour adventure in\nthe mysterious\nL-Esta Zone!"
    ),
    (2, 0, 23): "Taiki!\nCome on, wake up!",
    (2, 0, 24): (
        "Oh, good. You're\nall safe.\nI had this awful\ndream where Akari\ngot captured."
    ),
    (2, 0, 25): (
        "Quit sleep-talking!\nWe are captured!\nDon't you remember?\nWe came here, found\nthe Digimon calling\nfor help, and then--\nZAP!\nThose creeps knocked\nus all out!"
    ),
    (2, 0, 26): (
        "Then where are\nShoutmon and the\nothers?\nYou don't think..."
    ),
    (2, 0, 27): (
        "They must've been\ntaken while we were\nout cold.\nSo what's the plan,\nTaiki?"
    ),
    (2, 0, 28): (
        "What do you think?\nWe're saving them!"
    ),
    (2, 0, 29): (
        "Of course we are.\nThat's always your\nanswer: save this,\nrescue that...\nNews flash, Taiki:\nwe're the ones who\nneed rescuing!"
    ),
    (2, 0, 30): (
        "That voice we heard\nsaid the same thing:\n'I have to save\neveryone.'\nIt hit way too close\nto home.\nI couldn't ignore it."
    ),
    (2, 0, 31): "Hey! Sorry I took\nso long!",
    (2, 0, 32): (
        "Aah! You're that\nDigimon from before!"
    ),
    (2, 0, 33): (
        "The one who called\nus here for help!"
    ),
    (2, 0, 34): (
        "Shh! Keep it down!\n\nFollow me before\nsomebody spots us!"
    ),
    (2, 0, 35): (
        "W-wait a second!\nWhat're you doing\nhere?"
    ),
    (2, 0, 36): (
        "You came to rescue\nus, didn't you?\nThen rescuing you\nis only fair!\nI'm Spadamon.\nThanks for coming."
    ),
    (2, 0, 37): (
        "We're the ones who\nshould thank you.\nI'm Taiki Kudo.\nThis is Akari, and\nthat's Zenjirou."
    ),
    (2, 0, 38): (
        "...Someone's coming!\nStay right there!"
    ),
    (2, 0, 39): (
        "Hey, prisoners!\nLook who I brought\nwith me!"
    ),
})

# Batch 2A: global prose records 500-574 (1,027 draft-English words).
# Spadamon's rescue, formation tutorial, and the Skyfort prison scene.
OVERRIDES.update({
    (2, 2, 100): (
        "It's no use, Spadamon! You think you can escape?\n"
        "The El Estou Zone already belongs to ROG!\n"
        "Lord Minotaurmon, one of our officers, has even invaded Skyfort!\n"
        "A weakling like you can't do a thing now.\n"
        "You have only one choice: submit to ROG!"
    ),
    (2, 2, 101): (
        "S-stop it! Just leave me alone!\n"
        "I don't know anything about whatever you ROG invaders are looking for!\n"
        "Please, just go away!"
    ),
    (2, 2, 102): (
        "That's him!\nEveryone, we've gotta save that Digimon!\n"
        "He called out to me for help. I can't just abandon him!"
    ),
    (2, 2, 103): "Huh? Who are you?!",
    (2, 2, 104): "You still had allies?",
    (2, 2, 105): "No. We already captured all of his friends... didn't we?",
    (2, 2, 106): (
        "Then who are they?!\nAnd one of them doesn't even look like a Digimon..."
    ),
    (2, 2, 107): (
        "I don't care who you are or where you came from!\n"
        "You'll learn what happens to fools who defy ROG!"
    ),
    (2, 2, 108): (
        "Um... Taiki?\nSorry to interrupt, but are we really rescuing someone "
        "when we don't even know who he is?"
    ),
    (2, 2, 109): "When somebody's in trouble right in front of you, you can't ignore it!",
    (2, 2, 110): (
        "...Yeah, you're right. I shouldn't have asked.\n"
        "He's obviously in serious trouble. Let's hurry and help him!"
    ),
    (2, 2, 111): "Lay a hand on him, and you'll have to deal with us!",
    (2, 2, 112): (
        "To gain the advantage in battle, think carefully about your formation.\n"
        "The Digimon fighting in the center is the Vanguard.\n"
        "It can deal heavy damage with combat skills and use powerful combo attacks!"
    ),
    (2, 2, 113): (
        "The Digimon supporting the Vanguard from below are called the Rear Guard.\n"
        "Rear Guard Digimon don't take enemy attacks, but they can't use combo attacks, "
        "and their combat skills deal only half the Vanguard's damage.\n"
        "You also can't place Digimon in the Rear Guard unless a Vanguard is set."
    ),
    (2, 2, 114): "Would you like me to explain it again?",
    (2, 2, 115): "Explain it again",
    (2, 2, 116): "Start the battle",
    (2, 2, 117): "All right, everyone! Let's try this again!\nDigiXros!",
    (2, 2, 118): (
        "Whew... That was scary. Thanks for saving me...\n"
        "...Um, who are you?\nY-you're not another enemy who's after me, are you?!"
    ),
    (2, 2, 119): "Huh?\nYou're the one who called us here...",
    (2, 2, 120): "That's far enough!",
    (2, 2, 121): "Back away! Don't take another step!",
    (2, 2, 122): "...Huh? Kiriha?!",
    (2, 2, 123): "Wait, Kiriha! What the heck is going on?!",
    (2, 2, 124): (
        "Sorry, but I'm not handing this Digimon over to you.\n"
        "He's the key I need to reach even greater heights."
    ),
    (2, 2, 125): "...What do you mean?",
    (2, 2, 126): (
        "Something's weird. What's gotten into you, Kiriha?\n"
        "I thought becoming Taiki's rival had mellowed you out, "
        "but now you're back to your cold, scary self..."
    ),
    (2, 2, 127): (
        "What you think of me is irrelevant.\nJust stand there and watch."
    ),
    (2, 2, 128): "Now come quietly. I'd rather not get rough.",
    (2, 2, 129): (
        "I don't know who you are, but quit ordering me around!\n"
        "I'm escaping with my friends. I'm not going anywhere with you!"
    ),
    (2, 2, 130): "Wh-what is this?!",
    (2, 2, 131): "Did we get him?",
    (2, 2, 132): "All right! Everyone, capture them all!",
    (2, 2, 133): (
        "We'll show you exactly what happens to anyone who opposes ROG!"
    ),
    (2, 2, 134): (
        "Hmph. I expected more resistance.\n"
        "Even with the element of surprise, that was disappointingly easy."
    ),
    (2, 2, 135): (
        "...Tch. Of all the times for this to happen!\n"
        "We have no choice but to retreat for now."
    ),
    (2, 2, 136): "A-are you okay?! Hey, stay with me!",
    (2, 2, 137): "They're going to catch us at this rate!\nS-sorry!",
    (2, 2, 138): "They got away. Are you just letting them go?",
    (2, 2, 139): (
        "I can't do everything myself!\n"
        "If I don't take down the strongest threats first, we'll be the ones in danger.\n"
        "Spadamon can wait. We captured all his friends.\n"
        "He'll come right back when he tries to rescue them."
    ),
    (2, 2, 140): "Take these prisoners inside Skyfort!",
    (2, 2, 141): "Taiki! Taiki, wake up!",
    (2, 2, 142): (
        "Oh, good. Is everyone okay?\n"
        "I dreamed Akari had been captured by some bad guys."
    ),
    (2, 2, 143): "Wake up, sleepyhead! We're definitely not okay!",
    (2, 2, 144): (
        "Akari and everyone here were captured by those nasty ROG creeps."
    ),
    (2, 2, 145): (
        "...So your dream wasn't actually that far off, Taiki."
    ),
    (2, 2, 146): "Where are Shoutmon and the others?",
    (2, 2, 147): (
        "They must've been taken somewhere while we were unconscious.\n"
        "Ballistamon, Dorulumon, and Cutemon are all gone."
    ),
    (2, 2, 148): "They took almost everyone. What are we going to do now?",
    (2, 2, 149): "What do you think? We're rescuing them!",
    (2, 2, 150): "Right now, we're the ones who could use some rescuing.",
    (2, 2, 151): (
        "You really do want to save everyone, don't you, Taiki?\n"
        "Well, I guess that's one of your best qualities."
    ),
    (2, 2, 152): (
        "The voice I heard on the way here said the same thing: "
        "that I had to save everyone.\n"
        "It felt personal. I couldn't just ignore it."
    ),
    (2, 2, 153): "...Oh! You're the Digimon from before! They locked you up here too?",
    (2, 2, 154): "Whoa! You're that Digimon from before?!",
    (2, 2, 155): "D-don't shout! The ROG guards will find us!",
    (2, 2, 156): "W-wait a second. Forget that--why are you here?",
    (2, 2, 157): (
        "I came to rescue my friend Patamon, but he doesn't seem to be here.\n"
        "I'm Spadamon. Who are you?"
    ),
    (2, 2, 158): "I'm Taiki Kudo. These are Akari and Zenjirou.",
    (2, 2, 159): "We're Starmon and...",
    (2, 2, 160): "...the Pickmons! Nice to meet you!",
    (2, 2, 161): "Someone's coming! Don't move!",
    (2, 2, 162): "Hey, you lot! We brought your friends!",
    (2, 2, 163): (
        "Dumb punks put this annoying door on here.\n"
        "No matter what I do, it won't budge.\n"
        "It looks flimsy, but it's a solid Protection Block.\n"
        "Guess I'm the only one who can put these prisoners in or take them out."
    ),
    (2, 2, 164): "Shoutmon! Are you okay?!",
    (2, 2, 165): (
        "You aren't getting out, so don't try anything funny!\n"
        "Defy us again and neither you nor your friends will get off so easily!"
    ),
    (2, 2, 166): "Shoutmon, are you okay?!",
    (2, 2, 167): "Hey, Shoutmon!",
    (2, 2, 168): "Wake up, brother!",
    (2, 2, 169): "Shoutmon!!",
    (2, 2, 170): (
        "...Taiki! We've got a serious problem!\n"
        "They took Ballistamon somewhere.\n"
        "They said they'd put the Digimon into some kind of machine...\n"
        "If we want our friends back, they said to hand over Spadamon."
    ),
    (2, 2, 171): "...Spadamon. That's me.",
    (2, 2, 172): (
        "...Huh? You're that Digimon from before.\nI thought you escaped."
    ),
    (2, 2, 173): (
        "I couldn't help it! I'm weak...\n"
        "ROG suddenly invaded Skyfort. Everyone was supposed to escape together, "
        "but everything fell apart...\nBut..."
    ),
    (2, 2, 174): (
        "Patamon stayed behind to protect Skyfort.\n"
        "He's my best friend, and he's way too responsible for his own good.\n"
        "I told him to run, but he insisted on fighting to the end.\n"
        "ROG will capture him soon too!\nYou're strong, right? Please help me!"
    ),
})

# Batch 2B: global prose records 575-619 (1,005 draft-English words).
# Spadamon joins, battle-command tutorial, and DigiLab rescue.
OVERRIDES.update({
    (2, 2, 175): (
        "Of course, Spadamon! We're Xros Heart--a team of Digimon with fiery hearts!\n"
        "We're a little short-handed right now, but we still can't ignore someone in trouble!"
    ),
    (2, 2, 176): "That's our Taiki! I knew you'd say that!",
    (2, 2, 177): (
        "Now we just need to get through this door.\n"
        "Spadamon, know any way out?"
    ),
    (2, 2, 178): (
        "That's easy. This place belonged to us before ROG stole it."
    ),
    (2, 2, 179): (
        "All right, let's move!\nI'm gonna knock those creeps into next week!"
    ),
    (2, 2, 180): "Shoutmon and Spadamon joined the party!",
    (2, 2, 181): (
        "They say an incredible power is hidden in this Zone.\n"
        "Where is it, and what exactly is it?!"
    ),
    (2, 2, 182): (
        "I-I don't know! How would I?!\n"
        "If we had power like that, we'd have driven you out ages ago!"
    ),
    (2, 2, 183): (
        "...Yeah, good point. Maybe it doesn't exist after all.\n"
        "Everything we've found has been a disappointment.\n"
        "You useless liars have outlived your purpose!\n"
        "I'll toss you all over the edge and see if you can fly!"
    ),
    (2, 2, 184): "Stop!",
    (2, 2, 185): "L-leave Patamon alone, or you'll answer to me!",
    (2, 2, 186): (
        "...Your voice cracked so badly I could barely understand you.\n"
        "The most spoiled brat in the Zone finally shows his face and starts acting tough?\n"
        "Who was the coward who abandoned his friends and ran away?"
    ),
    (2, 2, 187): (
        "Still, you saved me the trouble of finding you.\n"
        "Now I can deliver you to Lord Minotaurmon.\n"
        "For some reason, all of ROG is searching for you.\n"
        "Once Lord Minotaurmon recognizes my talent, I'll shoot straight into the officer ranks! Woo-hoo!"
    ),
    (2, 2, 188): (
        "Wh-what do I do?! They really are after me!\n"
        "I wanna run... but I have to save Patamon...\n"
        "Shoutmon! Taiki! What should I do?!"
    ),
    (2, 2, 189): (
        "Oh, come on! Make up your mind!\n"
        "Don't worry--our General has your back!"
    ),
    (2, 2, 190): (
        "A Digimon's survival depends on its General!\n"
        "Use the lower screen to give your Digimon commands!"
    ),
    (2, 2, 191): (
        "Commands are issued through the Command Ring.\n"
        "Press Left or Right on the +Control Pad to rotate it, then press A to select a command."
    ),
    (2, 2, 192): (
        "Choose FIGHT for an attack that doesn't consume MP.\n"
        "Use it whenever you want to conserve MP."
    ),
    (2, 2, 193): (
        "Choose SKILL to use special attacks that consume MP.\n"
        "Skills can hit groups or deal elemental damage.\n"
        "Strike an enemy with its elemental weakness to deal twice the normal damage!"
    ),
    (2, 2, 194): (
        "Choose DIGIXROS to fuse Digimon.\n"
        "You must first learn a fusion skill and have every required Digimon in your party."
    ),
    (2, 2, 195): (
        "Choose ITEM to use consumable items.\n"
        "Items can cure paralysis, sleep, and confusion, restore HP or MP, and revive fallen Digimon."
    ),
    (2, 2, 196): (
        "Choose TACTICS to let a Digimon battle automatically.\n"
        "FULL POWER uses the strongest attack that can defeat a target.\n"
        "CONSERVE uses only MP-free combat skills.\n"
        "GUARD focuses completely on defense.\n"
        "ESCAPE attempts to flee. If even one Digimon succeeds, the whole party escapes."
    ),
    (2, 2, 197): (
        "Choose FORMATION to swap the selected Digimon with another party member."
    ),
    (2, 2, 198): (
        "One last thing--remember this!\n"
        "Press B to redo your commands. When you're ready, press X to begin the battle!"
    ),
    (2, 2, 199): "Would you like me to explain that again?",
    (2, 3, 0): "Explain it again",
    (2, 3, 1): "Start the battle",
    (2, 3, 2): "All right, everyone! Let's try this again!\nDigiXros!",
    (2, 3, 3): "We're right here with you! Let's fight together!\nLet's go!",
    (2, 3, 4): "Spadamon! Thank goodness you're safe!",
    (2, 3, 5): (
        "P-Patamon! Patamooon!\nI'm so glad! I was scared you might be..."
    ),
    (2, 3, 6): (
        "D-don't say something so awful!\n"
        "I'm amazed you avoided getting captured by ROG, Spadamon.\n"
        "...And who are these Digimon?"
    ),
    (2, 3, 7): (
        "We're Xros Heart, from another Zone.\n"
        "Spadamon wanted to rescue you, so we decided to help."
    ),
    (2, 3, 8): (
        "I see... Thank you so much!\n"
        "What an incredible team! I'm so glad you protected Spadamon.\n"
        "If ROG had captured him, something much worse would've happened."
    ),
    (2, 3, 9): (
        "Something worse?\n"
        "That ROG soldier said their entire organization was searching for Spadamon.\n"
        "What does that mean?"
    ),
    (2, 3, 10): (
        "I-I don't know either!\n"
        "The truth is, I've lost my memory. I can't remember anything from before I met Patamon.\n"
        "Maybe I know some secret about this Zone or something...\nJ-just kidding!"
    ),
    (2, 3, 11): "Whoa, whoa, whoa! Are you seriously okay?!",
    (2, 3, 12): (
        "But ROG sounds like a huge organization.\n"
        "They wouldn't mobilize that many troops over nothing.\n"
        "Spadamon, do you really remember nothing?"
    ),
    (2, 3, 13): (
        "I-I really don't!\n"
        "Everyone says getting stronger might bring my memories back, "
        "but I've spent all this time running away, so I never got stronger. Tee-hee!"
    ),
    (2, 3, 14): (
        "Graaah! I can't take it anymore!\n"
        "Taiki and I are gonna pound some courage into you!"
    ),
    (2, 3, 15): (
        "Ha! I can't tell whether you're strong or weak.\n"
        "But the voice that called us here was real. I could feel how badly you wanted to save your friends."
    ),
    (2, 3, 16): (
        "...Oh, right! We can talk later!\n"
        "ROG activated the DigiLab system. They're planning a fusion experiment in the central room!"
    ),
    (2, 3, 17): "...Huh? Fusion? You mean DigiXros?",
    (2, 3, 18): (
        "...DigiXros?\nNo, DigiLab fuses Digimon together to power them up into a stronger Digimon.\n"
        "It's normally a really useful system, but ROG doesn't know how to operate it.\n"
        "That square Digimon who belongs to your team--they're going to use him as a test subject!"
    ),
    (2, 3, 19): "I'm coming too! Hurry to the central room!",
})

# Batch 2C: global prose records 620-686 (1,006 draft-English words).
# Ballistamon rescue, Minotaurmon battle, and Commander Room handoff.
OVERRIDES.update({
    (2, 3, 20): (
        "Why'd they drag this big lug all the way here?\n"
        "He's heavy, huge, slow-looking, stubborn, and hard to handle.\n"
        "Worst of all, his whole thing kinda overlaps with mine..."
    ),
    (2, 3, 21): "How?! We aren't alike by even one micron!",
    (2, 3, 22): (
        "Oh, shut up and haul him over to that machine!\n"
        "I'm taking his power and toughness for myself.\n"
        "Then nobody will ever call me a chicken again!"
    ),
    (2, 3, 23): "Hey... There are two machines here. Which one is it?",
    (2, 3, 24): (
        "H-how should I know?! The database only says the machine is in this room.\n"
        "Most of the local Digimon ran away, so we can't ask them.\n"
        "Maybe we should catch that Spadamon and squeeze the answer out of him..."
    ),
    (2, 3, 25): (
        "Idiot! Spadamon goes straight to Lord Minotaurmon when we find him.\n"
        "Figure this out yourself. Try to remember a clue!"
    ),
    (2, 3, 26): (
        "It's some secret system found only in this Zone.\n"
        "Apparently it mixes Digimon together and makes them way stronger."
    ),
    (2, 3, 27): (
        "Touch the switch in front of the machine, and it goes flash and makes a little jingle."
    ),
    (2, 3, 28): "...So which of these two looks like that?",
    (2, 3, 29): "They both kinda do... and kinda don't.",
    (2, 3, 30): (
        "What kind of clue is 'flash' and 'jingle'?! That tells us nothing!\n"
        "Forget it. Just pick one and mess with it."
    ),
    (2, 3, 31): (
        "Easy for you to say! What if we fiddle with it and they fuse all wrong?\n"
        "Why don't you two test it? One squishy, one rock-hard--average them out "
        "and you might get the perfect firmness!"
    ),
    (2, 3, 32): (
        "You're the one talking nonsense, birdbrain!\nKeep it up and I'll rip out that crest!"
    ),
    (2, 3, 33): "Taiki! It's Ballistamon!",
    (2, 3, 34): "He's okay--just unconscious. We made it in time!",
    (2, 3, 35): "Hang on, Ballistamon! Just a little longer!",
    (2, 3, 36): (
        "You've done whatever you wanted long enough!\n"
        "We're paying you back a million times over!"
    ),
    (2, 3, 37): "Wake up, Ballistamon! We came to rescue you!",
    (2, 3, 38): "Ballistamon!!",
    (2, 3, 39): "...Taiki. I knew you'd come.",
    (2, 3, 40): "Of course! You knew I wouldn't leave you here!",
    (2, 3, 41): "...Yeah. Thanks. You saved me.",
    (2, 3, 42): "Thank goodness! Is everyone okay?!",
    (2, 3, 43): (
        "More or less. But if we don't defeat their boss, ROG will occupy Skyfort again."
    ),
    (2, 3, 44): "Ballistamon, where's their boss?",
    (2, 3, 45): "In the room up ahead.",
    (2, 3, 46): (
        "Everyone, be careful. Their boss, Minotaurmon, is far stronger than anyone we've fought so far."
    ),
    (2, 3, 47): "I don't care who he is. Xros Heart won't lose!",
    (2, 3, 48): (
        "Hmm... If DigiLab and DigiFarm worked, they could help us.\n"
        "Both systems are completely offline, so I can't restart them immediately.\n"
        "Then again, that's probably why your friend wasn't harmed."
    ),
    (2, 3, 49): "What are DigiLab and DigiFarm?",
    (2, 3, 50): "DigiLab is where you gather and raise allies.",
    (2, 3, 51): "DigiFarm is where you train Digimon to become stronger.",
    (2, 3, 52): (
        "Use both systems well, and Digimon can greatly increase their power.\n"
        "While you defeat the Digimon in the Commander Room, I'll stay here and inspect the systems."
    ),
    (2, 3, 53): (
        "...I still don't totally understand, but protecting Skyfort comes first!\n"
        "Come on, everyone!"
    ),
    (2, 3, 54): "Ballistamon joined the party!",
    (2, 3, 55): "Hey, you! Are you ROG's boss?!",
    (2, 3, 56): (
        "...Hmm? Who are you?\nNobody barges into my Skyfort and gets away with it!"
    ),
    (2, 3, 57): "You're the ones who barged in here!",
    (2, 3, 58): (
        "Driving out the Digimon who live here by force is unforgivable!\n"
        "You'll face Koto's greatest swordsman, Zenjirou Tsurugi... and his friends!"
    ),
    (2, 3, 59): (
        "You don't understand. I am Minotaurmon the Quake, ROG's powerful leader!\n"
        "Get lost before I crush you like insects!"
    ),
    (2, 3, 60): "Y-you're the ones leaving! Give us back our Skyfort!",
    (2, 3, 61): (
        "Y-you're Spadamon! I heard you escaped...\n"
        "Fwahaha! And now you deliver yourself to me!\n"
        "Capturing you will fulfill the ambition of ZDMillenniummon, ROG's supreme leader: "
        "conquering the world with the Legendary Ancient Weapon!"
    ),
    (2, 3, 62): "ROG's supreme leader, ZDMillenniummon?",
    (2, 3, 63): "The Legendary Ancient Weapon...?",
    (2, 3, 64): "Enough talk! Spadamon, prepare yourself!",
    (2, 3, 65): "Heh! Bring it on!\nI'm counting on you, Taiki!",
    (2, 3, 66): "Now you know the power of Xros Heart!",
    (2, 3, 67): (
        "Guh... I never imagined Spadamon had allies like you.\n"
        "But you're mere children before Lord ZDMillenniummon!\n"
        "Enjoy your time with that powerless Spadamon while you can!"
    ),
    (2, 3, 68): "What did you say?!",
    (2, 3, 69): (
        "You'll understand your foolishness soon enough.\n"
        "But by the time you do, it will already be too late for everything."
    ),
    (2, 3, 70): (
        "...What a jerk! And who just lost to that 'powerless Spadamon,' huh?"
    ),
    (2, 3, 71): "...Huh? Spadamon, what's wrong?",
    (2, 3, 72): "Part of Spadamon's abilities returned!",
    (2, 3, 73): "Wh-what was that?! What just happened?",
    (2, 3, 74): "Are you okay, Spadamon?",
    (2, 3, 75): (
        "I-I remembered! The Legendary Ancient Weapon is a secret sealed in the El Estou Zone!\n"
        "Someone told me never, ever to tell anyone... I think...\n..."
    ),
    (2, 3, 76): "...Huh? What is it?",
    (2, 3, 77): (
        "That's all I remember. But it's absolutely secret!\n"
        "The Legendary Ancient Weapon being hidden in this Zone is totally, completely--\n"
        "Ah! I just told everybody! Wh-what do I do?!"
    ),
    (2, 3, 78): (
        "It's okay, Spadamon. Everyone here is on your side.\n"
        "You sure are strange. You were fighting so fiercely a minute ago...\n"
        "Wait! Maybe your memory returned because fighting made you stronger!"
    ),
    (2, 3, 79): "...I got stronger?",
    (2, 3, 80): (
        "Amazing! You really defeated him!\nHe was terrifying. That battle must've been tough!"
    ),
    (2, 3, 81): "Hmph. It wasn't that hard.",
    (2, 3, 82): "Zenjirou, you didn't do anything.",
    (2, 3, 83): "We've reclaimed this room, but who used it before?",
    (2, 3, 84): (
        "It's the Commander Room, used by the Zone's commander.\n"
        "I'd like Taiki and his team to use it. After all, Taiki is the El Estou Zone's commander now!"
    ),
    (2, 3, 85): "You can accept Request Quests from that monitor.",
    (2, 3, 86): (
        "And the recovery bed in the back restores all allied Digimon's HP and MP."
    ),
})

# Batch 2D: global prose records 687-746 (1,023 draft-English words).
# Energy Continent briefing and Capacitor Tower crisis.
OVERRIDES.update({
    (2, 3, 87): (
        "...Huh? Taiki looks more exhausted than the Digimon.\n"
        "We can explain everything later. Why don't you rest on the recovery bed?"
    ),
    (2, 3, 88): (
        "She's right! You always push yourself too hard, Taiki.\n"
        "Get some rest first. We can talk afterward!"
    ),
    (2, 3, 89): "Yeah... Now that you mention it, I'm suddenly... sleepy...",
    (2, 3, 90): "Good morning, Taiki.",
    (2, 3, 91): "Huh? Why the puzzled look?",
    (2, 3, 92): "...Hmm? Akari, I feel dizzy. Did I sleep too long?",
    (2, 3, 93): (
        "You're fine. The room really is moving.\n"
        "Skyfort is flying toward a place called the Energy Continent."
    ),
    (2, 3, 94): (
        "This island can move? You scared me...\nSo what's the Energy Continent like?"
    ),
    (2, 3, 95): (
        "It's the largest landmass, right in the center of this Zone.\n"
        "Digimon from other Zones think the Energy Continent is the entire El Estou Zone.\n"
        "Most of ROG's main force went there too.\n"
        "Many of our friends should be there, but we don't know where they are or whether they're safe."
    ),
    (2, 3, 96): (
        "Your friends are there? Then we need to find them quickly.\n"
        "How long until we reach the Energy Continent?"
    ),
    (2, 3, 97): "Well...",
    (2, 3, 98): (
        "Patamon will explain in the central room. He's been waiting for you to wake up."
    ),
    (2, 3, 99): "Ha-ha... Sorry. Looks like I overdid it again.",
    (2, 3, 100): (
        "It's okay. We need you healthy, Taiki.\n"
        "There was nothing else to do while the island was flying, so we made sure you recovered fully.\n"
        "Everyone's counting on you that much."
    ),
    (2, 3, 101): "Leave it to me! And thanks, Akari. As always.",
    (2, 3, 102): (
        "Hmm, Taiki and Akari are... Never mind.\n"
        "I'll tell Patamon you're awake. Come join us soon!"
    ),
    (2, 3, 103): "All right, let's go!",
    (2, 3, 104): (
        "Wait, Taiki! What are you doing?\n"
        "ROG's boss isn't this way. Ballistamon said he's past the room we were just in.\n"
        "Let's charge in and knock him flat!"
    ),
    (2, 3, 105): (
        "Good morning, Taiki. Sorry to ask so soon, but there's something we really need you to do."
    ),
    (2, 3, 106): (
        "I already heard. Leave it to us!\n"
        "We'll land on the Energy Continent and find your friends.\n"
        "If most of ROG is there too, we definitely can't ignore it. We'll head out right away!"
    ),
    (2, 3, 107): (
        "Just don't get so worked up that you collapse again.\n"
        "You're always saying you can't ignore people in trouble, but you're the one I worry about most!"
    ),
    (2, 3, 108): "I'll be careful. Thanks, Akari.",
    (2, 3, 109): "So... how do we get to the Energy Continent?",
    (2, 3, 110): (
        "Aren't we flying toward it now? Can't we just land when we arrive?"
    ),
    (2, 3, 111): (
        "Skyfort can fly near the continent, but it can't land on the ground.\n"
        "We've never tried, but it would probably crash and break apart."
    ),
    (2, 3, 112): "Then how did you travel before?",
    (2, 3, 113): "I've got it, brother! We fly over it, then jump down from way up--",
    (2, 3, 114): "...Only Starmon and the Pickmons could survive that.",
    (2, 3, 115): (
        "Dang it! If Sparrowmon were here, DigiXros could let us fly!\n"
        "Where did she go?!"
    ),
    (2, 3, 116): (
        "Here in the El Estou Zone, we travel between islands with the Digimon Flight Corps--"
        "flying Digimon who carry passengers."
    ),
    (2, 3, 117): (
        "But they hid somewhere when ROG invaded. Can you find them for us?"
    ),
    (2, 3, 118): "Sure, Patamon. Do you have any clues?",
    (2, 3, 119): (
        "All we know is that they're somewhere on Skyfort.\n"
        "I'll give you a detailed map. You can view it by selecting MAP on your Xros Loader."
    ),
    (2, 3, 120): "Obtained a key item!\nMap 01",
    (2, 3, 121): "Obtained a key item!\nMap 02",
    (2, 3, 122): (
        "We should stay on Skyfort and help Patamon.\n"
        "If any machines need fixing, leave them to Zenjirou Tsurugi!"
    ),
    (2, 3, 123): (
        "Taiki, if your Digimon run low on HP or MP, use a Tent or Skyfort's recovery bed.\n"
        "A rest in the bed will restore everyone!"
    ),
    (2, 3, 124): (
        "The request to find the Digimon Flight Corps should be available.\n"
        "Could you accept it from the Quest Monitor first?"
    ),
    (2, 3, 125): "Quest Monitor...?",
    (2, 3, 126): (
        "It's the large digital monitor in the Commander Room.\n"
        "Ask the Palmon beside it how to use it."
    ),
    (2, 3, 127): (
        "Taiki can handle anything perfectly! Whatever that monitor thing is, leave it to him!"
    ),
    (2, 3, 128): "Woo! Looking cool, brother!",
    (2, 3, 129): (
        "I-I'm coming too! Being with Taiki's team feels like it might help me recover my lost memories."
    ),
    (2, 3, 130): (
        "I know it's a lot, Taiki, but please look after Spadamon.\n"
        "I'll keep repairing the systems and collecting data. I'll be here if you have questions."
    ),
    (2, 3, 131): "All right. Let's go!",
    (2, 3, 132): "Hmmm...",
    (2, 3, 133): "Mmmm...",
    (2, 3, 134): "Grrrr...",
    (2, 3, 135): "Why is everyone standing around groaning?",
    (2, 3, 136): "Taiki! Perfect timing.",
    (2, 3, 137): "We've been waiting, Taiki Kudo!",
    (2, 3, 138): (
        "What's wrong? Is there trouble, Akari?\n"
        "Need hands, brains, or muscle? Whatever it is, I'm ready!"
    ),
    (2, 3, 139): "What's going on, Zenjirou? Patamon?",
    (2, 3, 140): "...Starmon, Shoutmon, calm down.",
    (2, 3, 141): "What's wrong, Patamon?",
    (2, 3, 142): (
        "I checked Skyfort's systems and found we don't have enough energy.\n"
        "None of DigiLab or DigiFarm's important functions work.\n"
        "Worse, if we don't restart the Capacitor Towers soon, the entire system will run out of energy and shut down."
    ),
    (2, 3, 143): "Capacitor Towers?",
    (2, 3, 144): (
        "They generate energy for this Zone. There are six, but they all stopped.\n"
        "They worked before Skyfort was captured. Did Minotaurmon tamper with something?"
    ),
    (2, 3, 145): (
        "Did ROG cut Skyfort's power so they could take it?! What a dirty trick!"
    ),
    (2, 3, 146): (
        "But each Capacitor Tower has a huge door, and the system is behind it.\n"
        "Only a tower administrator should be able to operate it.\n"
        "That's why ROG has heavily fortified every tower."
    ),
})

# Batch 2E: global prose records 747-811 (1,010 draft-English words).
# Pukumon battle, Ancient Weapon lore, and Chibickmon disappearance.
OVERRIDES.update({
    (2, 3, 147): "Who administers the Capacitor Towers?",
    (2, 3, 148): (
        "Who knows? The Capacitor Towers have always been sealed.\n"
        "Patamon and I once tried sneaking inside, but the door wouldn't budge.\n"
        "We finally went home crying--I mean, that was ages ago!\n"
        "I wouldn't cry now! Really!"
    ),
    (2, 3, 149): (
        "But the system behind that door shut down, which stopped the energy flow, right?\n"
        "We still have to investigate the Capacitor Towers."
    ),
    (2, 3, 150): (
        "Yeah. Something must've happened there, so let's investigate first.\n"
        "Where's the nearest Capacitor Tower?"
    ),
    (2, 3, 151): (
        "Let's see... I think it's at Knuckle Coast, on the edge of the Energy Continent."
    ),
    (2, 3, 152): "Whoa! That name sounds tough! I'm itching for action!",
    (2, 3, 153): "ROG may be there, so we'd better prepare carefully.",
    (2, 3, 154): (
        "You may have noticed, but the Penguinmon in the central room sells recovery items and equipment.\n"
        "We'll stay here and keep helping Patamon!"
    ),
    (2, 3, 155): (
        "Be careful, Taiki. Don't push yourself too hard.\n"
        "If HP or MP gets low outside, find a Tent Point and rest on its recovery bed."
    ),
    (2, 3, 156): (
        "To travel, board the Digimon Flight Corps at the Skyport behind the Commander Room."
    ),
    (2, 3, 157): (
        "All right, Taiki! Let's go! We'll fly and fly and fly with the Digimon Flight Corps!"
    ),
    (2, 3, 158): "Brother, did you always love flying this much?",
    (2, 3, 159): "I don't like it...",
    (2, 3, 160): "Still, this is kinda exciting! All right, let's depart!",
    (2, 3, 161): (
        "You're not from the El Estou Zone... You're ROG!\nWere you waiting to ambush us?"
    ),
    (2, 3, 162): (
        "Well, well. Spadamon, keeper of the El Estou Zone's secrets.\n"
        "You could've stayed hidden, yet you came here to be captured.\n"
        "You're painfully ridiculous and laughably foolish. Puh-kuh-kuh!"
    ),
    (2, 3, 163): (
        "So true, so true, so very true! Lord Pukumon is always right!\n"
        "This fool certainly doesn't look like someone who knows the secret of the Legendary Ancient Weapon!"
    ),
    (2, 3, 164): (
        "But if this puny Spadamon really knows the secret, we'll simply snatch him up!"
    ),
    (2, 3, 165): "...These fishy freaks sure flap their mouths like they're important.",
    (2, 3, 166): "Ugh, they're so annoying! I'm not weak anymore!",
    (2, 3, 167): (
        "Pukumon! What is ROG after? Why are you trying to capture Spadamon?!"
    ),
    (2, 3, 168): (
        "ROG's objective? Puh-kuh-kuh!\nWorld domination, obviously!\n"
        "Once we find the Legendary Ancient Weapon, ROG will rule the world however we please!"
    ),
    (2, 3, 169): "Magnificent! What thrilling words! That's our Lord Pukumon!",
    (2, 3, 170): "ROG's Splash Leader, Pukumon the Prickle!",
    (2, 3, 171): "Puh-kuh-kuh!",
    (2, 3, 172): (
        "World domination? Is that why you're tormenting this Zone's Digimon?\n"
        "I'll never let you get away with it!"
    ),
    (2, 3, 173): (
        "I'll silence that smart mouth in a moment. Puh-kuh-kuh!"
    ),
    (2, 3, 174): (
        "Guh... Lord Pukumon, defeated by the likes of you?\nHow laughable. Puh-kuh-kuh!"
    ),
    (2, 3, 175): "What's so funny?!",
    (2, 3, 176): (
        "...We will never give up on Spadamon.\n"
        "Everything is for Lord ZDMillenniummon, leader of ROG!"
    ),
    (2, 3, 177): "Part of Spadamon's abilities returned!",
    (2, 3, 178): (
        "...I remember! The Legendary Ancient Weapon has terrifying power.\n"
        "They say an angel could use it to save the world, while a demon could destroy it.\n"
        "I thought it was only an old El Estou legend, but ROG invaded this Zone to find that weapon!"
    ),
    (2, 3, 179): (
        "Destroy the world? That can't be...\n"
        "But why would Spadamon know such an incredible secret?"
    ),
    (2, 3, 180): (
        "Maybe it's a mistake. Huge secrets like that shouldn't belong to some weak-looking guy like Spadamon.\n"
        "They should belong to someone kingly--like me!"
    ),
    (2, 3, 181): "...Huh? Did I say something weird?",
    (2, 3, 182): "Ha-ha-ha... He didn't mean any harm...",
    (2, 3, 183): "Ngh?! Hey, hey... Wh-what is this?! What's happening?!",
    (2, 3, 184): "...What's with you all of a sudden, Shoutmon?",
    (2, 3, 185): (
        "The Pickmons at Skyfort are--ow, ow, ow! My ears!"
    ),
    (2, 3, 186): "Your ears?",
    (2, 3, 187): (
        "They're yapping over the emergency channel!\n"
        "They're so frantic and panicked that I can't understand a word!"
    ),
    (2, 3, 188): "Something's seriously wrong, Taiki!",
    (2, 3, 189): (
        "ROG may be attacking again. Let's hurry back to Skyfort!"
    ),
    (2, 3, 190): "Taiki! Did you hear our transmission?!",
    (2, 3, 191): "It's terrible! Terrible!",
    (2, 3, 192): "It's terrible! Terrible!",
    (2, 3, 193): "What happened?",
    (2, 3, 194): (
        "We've got big trouble, brother! Chibickmon--the smallest Pickmon--was kidnapped!"
    ),
    (2, 3, 195): "Kidnapped? By whom? When? Why? Where did they take him?!",
    (2, 3, 196): (
        "We don't know! We looked away for just a second, and he vanished.\n"
        "S-sorry, brother. This happened even with us watching him..."
    ),
    (2, 3, 197): "Could he just be lost, or playing somewhere?",
    (2, 3, 198): (
        "No. If he won't answer the other Pickmons' calls, this isn't ordinary wandering."
    ),
    (2, 3, 199): (
        "The last Digimon to see him heard him say, 'Wait up, sis!'\n"
        "I think he followed someone."
    ),
    (2, 4, 0): "Sis? Could he mean Akari?",
    (2, 4, 1): (
        "No, he's never called Akari that, and she's in the Commander Room.\n"
        "It was probably someone he met in this Zone."
    ),
    (2, 4, 2): (
        "We asked around, and someone saw him near E-Knuckle City.\n"
        "He disappeared again soon afterward, so we don't know where he went next."
    ),
    (2, 4, 3): (
        "E-Knuckle City? That's near Knuckle Coast East, where we fought Pukumon."
    ),
    (2, 4, 4): "Let's go, brother! We have to find Chibickmon!",
    (2, 4, 5): "We're counting on you!",
    (2, 4, 6): "Count... on you! Huh?! Hey, I was supposed to say it first!",
    (2, 4, 7): (
        "...Without that little guy, the Pickmons are a mess.\n"
        "Leave it to us! We'll find him right away!"
    ),
    (2, 4, 8): "Let's hurry, Taiki! We have to save Chibickmon!",
    (2, 4, 9): (
        "Wait, Taiki! If you're going to Knuckle Coast East, take this!"
    ),
    (2, 4, 10): "What key is this?",
    (2, 4, 11): (
        "It opens the gate near E-Knuckle City. Beyond it is Spiral Amazon.\n"
        "If you can't find Chibickmon at Knuckle Coast East, could you search Spiral Amazon too?"
    ),
})

# Batch 2F: global prose records 812-912 (1,006 draft-English words).
# Minervamon, Melody Capture tutorial, and Chibickmon's return.
OVERRIDES.update({
    (2, 4, 12): "Spiral Amazon? Got it. We'll search there too.",
    (2, 4, 13): (
        "Oh, what the heck?! We passed this spot already!\n"
        "We're wandering around and around the same place!"
    ),
    (2, 4, 14): "Big sis, round and round!",
    (2, 4, 15): (
        "I told you, call me Lady Minervamon!\n"
        "And now that you've joined TEAM CUTIE, you have to say 'meow' before and after you speak!\n"
        "You understand?!"
    ),
    (2, 4, 16): "Meow! Yes, meow!",
    (2, 4, 17): "There he is! It's Chibickmon and... who's that? What are they doing?",
    (2, 4, 18): (
        "Uh... don't ask me. They look like they're having fun. Maybe she isn't a bad Digimon?"
    ),
    (2, 4, 19): "Hey, you! Dangerous bad boys are coming! Hurry and run!",
    (2, 4, 20): "Danger... meow? Bad boys...?",
    (2, 4, 21): "Shut up! Stand up! And hurry up!",
    (2, 4, 22): "M-meow! Yes, meow!",
    (2, 4, 23): "They got away...",
    (2, 4, 24): "Let's chase them, Taiki! We can still catch up!",
    (2, 4, 25): "Right!",
    (2, 4, 26): (
        "The whirlpools here only work one way.\n"
        "Once you enter one, you can't return through the whirlpool you emerge from. Be careful!"
    ),
    (2, 4, 27): "We should be able to hide here for a while--",
    (2, 4, 28): "...or not!",
    (2, 4, 29): "Not... not... meow?",
    (2, 4, 30): (
        "When there's a hole, I wanna be inside it!\n"
        "We'll make our meow-gnificent retreat! You understand?!"
    ),
    (2, 4, 31): "Meow! Retreat, meow!",
    (2, 4, 32): (
        "You're extra cute, so I'll use my special move and take you exploring underground!"
    ),
    (2, 4, 33): "Underground, meow!",
    (2, 4, 34): "Hey! What the heck was that?!",
    (2, 4, 35): (
        "That was the Dig ability, which lets a Digimon burrow underground.\n"
        "To follow them, Melody Capture a Digimon with Dig, materialize it at DigiLab, and put it in your party."
    ),
    (2, 4, 36): "Melody Capture? Materialize at DigiLab? I've heard that before... What was it?",
    (2, 4, 37): (
        "Defeat an unharmed Digimon in one hit, or finish it with a Melody-effect attack, and it may become Melody Data!\n"
        "Using an element it's weak against raises the chance. Using an element it resists lowers it.\n"
        "DigiLab can materialize collected Melody Data as Digimon!\n"
        "Um... that's all I remember. Ask Guilmon or Veemon at Skyfort for details..."
    ),
    (2, 4, 38): "Either way, we need more allies. Which Digimon have the Dig ability?",
    (2, 4, 39): (
        "Guilmon at Knuckle Coast, Dorumon in the mountains near Skyfort, and Tyrannomon around here should have Dig."
    ),
    (2, 4, 40): "Then let's regroup, Shoutmon.",
    (2, 4, 41): "All right...",
    (2, 4, 42): "Hey! We have a Digimon with Dig in the party!",
    (2, 4, 43): "Great! Let's hurry after them!",
    (2, 4, 44): (
        "We finally dug our way out of Ring Wandering, and it's still nothing but darkness ahead. Just like my life!"
    ),
    (2, 4, 45): "Wah... It's dark... So dark I'm getting dizzy...",
    (2, 4, 46): "M-m-m-my gosh! Something appeared! A ghost? Spirit? Monster?!",
    (2, 4, 47): "M-monster, meow?!",
    (2, 4, 48): (
        "Yeah! A terrifying monster that wants to catch and destroy us!\n"
        "Our only option is escape! You understand?!"
    ),
    (2, 4, 49): "Meow! Y-yes, meow?!",
    (2, 4, 50): "All right, run!",
    (2, 4, 51): "Dang it! We almost had them!",
    (2, 4, 52): (
        "Waaah! It's dark and scary here! Taiki! Shoutmon! Let's catch them and get out!"
    ),
    (2, 4, 53): "You're hopeless, Spadamon. Come on, let's keep chasing them!",
    (2, 4, 54): (
        "Beyond darkness waits more darkness. It's just like my life! Yee-haw!"
    ),
    (2, 4, 55): "What's wrong? You're trembling. Afraid of the dark?",
    (2, 4, 56): "I-I-I'm not scared at all!",
    (2, 4, 57): "B-b-b-b...",
    (2, 4, 58): (
        "Hey! TEAM CUTIE rule: when you're in trouble, laugh!\n"
        "When things get heavy or desperate, laugh them away! You understand?!"
    ),
    (2, 4, 59): "...M-meow! I'll laugh, meow!",
    (2, 4, 60): "Oh, you really are ridiculously cute!",
    (2, 4, 61): "TEAM CUTIE, forward! Let's charge!",
    (2, 4, 62): "Meow! Charge, meow!",
    (2, 4, 63): "We're so close to catching them...",
    (2, 4, 64): (
        "There you go, my squishy little friend! We're alive in this beautiful flower garden!"
    ),
    (2, 4, 65): "Chibickmon! Are you okay?!",
    (2, 4, 66): "Yay, Shoutmon! Chibickmon is fine!",
    (2, 4, 67): "After all the trouble we went through, this kid...",
    (2, 4, 68): "You can't escape this time. Give it up!",
    (2, 4, 69): "Ngh! You're so persistent! We'll make a speedy exit!",
    (2, 4, 70): (
        "This rock is in the way! I'll split it cleanly with Rock Breaker!"
    ),
    (2, 4, 71): (
        "Come to think of it, I don't know Rock Breaker.\n"
        "If I use spirit alone, the only thing splitting will be my knuckles!\n"
        "Owie, owie, go away!"
    ),
    (2, 4, 72): "...She's strange. Is she with ROG too?",
    (2, 4, 73): "I don't know. She doesn't look that evil.",
    (2, 4, 74): "Taiki, Shoutmon... Is that rock she tried to break moving?!",
    (2, 4, 75): "Grrrr...",
    (2, 4, 76): "...Meow!!",
    (2, 4, 77): (
        "What is that?! We're surrounded!\n"
        "Can't advance, can't retreat--this might be a seriously boring crisis!"
    ),
    (2, 4, 78): (
        "With all these interruptions, I have no choice.\n"
        "Squishy little friend, this is goodbye."
    ),
    (2, 4, 79): "Hey! Who are you, and why did you kidnap Chibickmon?!",
    (2, 4, 80): (
        "You call me 'who,' but who are you? And what's this about kidnapping?"
    ),
    (2, 4, 81): "Chibickmon was playing! Big sis is fun!",
    (2, 4, 82): "Did she do anything you didn't like, Chibickmon?",
    (2, 4, 83): "Nothing bad! Chibickmon likes big sis!",
    (2, 4, 84): (
        "Minerva-me had lots of fun too! But playtime is over. You need to go home!"
    ),
    (2, 4, 85): "Don't wanna go home! Wanna play!",
    (2, 4, 86): (
        "You've been a very good kid, so don't be selfish at the very end."
    ),
    (2, 4, 87): "Big sis... We'll play again...",
    (2, 4, 88): "If fate allows, we'll meet and play again. You understand?",
    (2, 4, 89): "...M-meow! Yes, meow!",
    (2, 4, 90): "You really are incredibly cute!",
    (2, 4, 91): "The cute part is fine, but... what about those?",
    (2, 4, 92): "GROOOAR!",
    (2, 4, 93): "Oof?!",
    (2, 4, 94): "Wh-meow?! I-I'm going home, meow!!",
    (2, 4, 95): "Wait, you seriously didn't notice them until now?",
    (2, 4, 96): "Maybe they'll understand if we talk... Probably not.",
    (2, 4, 97): "GROOOOAR!!",
    (2, 4, 98): "Talking won't work. We have to fight!",
    (2, 4, 99): "GROOOOAR!!",
    (2, 4, 100): "Guh... Grrrr... grr.",
    (2, 4, 101): "Meow! That was amazing! Meow-hoo!",
    (2, 4, 102): "Uh, are you starting to copy her weird speech?",
    (2, 4, 103): "Calling people weird makes you weird! You understand?",
    (2, 4, 104): (
        "W-well... we can discuss that later. Everyone's worried, so let's return to Skyfort."
    ),
    (2, 4, 105): "Meow! We're home, meow!",
    (2, 4, 106): "HEY!!",
    (2, 4, 107): (
        "Don't stroll in here saying 'meow'! Where was this little kid, and what was he doing?!"
    ),
    (2, 4, 108): "Playing with big sis!",
    (2, 4, 109): "What?! Do you have any idea how worried we were?!",
    (2, 4, 110): "How worried we were!!",
    (2, 4, 111): "Worried, meow!",
    (2, 4, 112): "Come on. The important thing is that we found him safely!",
})

# Batch 2G: global prose records 913-992 (1,005 draft-English words).
# Dorulumon/Cutemon rescue and approach to the next Capacitor Tower.
OVERRIDES.update({
    (2, 4, 113): (
        "W-well, yeah. At least it doesn't look like he was caught up in anything dangerous."
    ),
    (2, 4, 114): "Though that girl seemed dangerous in a completely different way.",
    (2, 4, 115): "Taiki, big sis gave me a present for you!",
    (2, 4, 116): "Obtained a key item!\nAmazon West Key",
    (2, 4, 117): "What's this? Where did you get it?",
    (2, 4, 118): (
        "It's the spinny key to Spiral Amazon! Big sis said to give it to Taiki!"
    ),
    (2, 4, 119): (
        "She said that? What does it mean? Did that Digimon know us?"
    ),
    (2, 4, 120): "Wait. Did she leave any other message?",
    (2, 4, 121): "A message? Um... Big sis said, 'Kyupon isn't Kyupon-ing.'",
    (2, 4, 122): "...I have absolutely no idea what that means.",
    (2, 4, 123): (
        "Taiki, I've got a bad feeling. This 'Kyupon' she keeps mentioning... "
        "Could she mean Cutemon?"
    ),
    (2, 4, 124): "But what does 'Cutemon isn't Cutemon-ing' mean?",
    (2, 4, 125): (
        "If Cutemon is there, Dorulumon should be too. Let's head into Spiral Amazon!"
    ),
    (2, 4, 126): "We'll stay here and give this kid a lecture!",
    (2, 4, 127): "A lecture!",
    (2, 4, 128): "Meow...",
    (2, 4, 129): (
        "Your missing friends were Cutemon and Dorulumon, right?\n"
        "I hope we find them safe in Spiral Amazon."
    ),
    (2, 4, 130): "They'll be fine. I'm sure they're managing. Come on, let's go!",
    (2, 4, 131): "...Dorulumon!",
    (2, 4, 132): "Dorulumon! What are you doing here?!",
    (2, 4, 133): "Taiki... Shoutmon... I'm sorry.",
    (2, 4, 134): (
        "Look! The big prey swallowed the bait whole!\n"
        "At last, it's doggy's turn to perform!"
    ),
    (2, 4, 135): "If I defeat them, you'll release Cutemon, right?",
    (2, 4, 136): (
        "Hmm-hmm! That's up to doggy!\nStop stalling and capture Spadamon already!"
    ),
    (2, 4, 137): "D-Dorulumon...",
    (2, 4, 138): "Stop struggling and behave, meow!",
    (2, 4, 139): "Stop whining and do what you're told, meow!",
    (2, 4, 140): (
        "Grr... Remember this, Minervamon. You won't get away with it!"
    ),
    (2, 4, 141): "Keep your mouth shut, doggy. Your breath smells when you talk!",
    (2, 4, 142): "Wait, Dorulumon. You're kidding, right?!",
    (2, 4, 143): (
        "I never expected to fight you like this... But I can't abandon Cutemon!"
    ),
    (2, 4, 144): (
        "Hmm-hmm! This is great!\n"
        "If everything goes well, ROG will find the Legendary Ancient Weapon and conquer the world! Yee-haw!"
    ),
    (2, 4, 145): (
        "This doggy is completely useless. How can I face Lord ZDMillenniummon now?"
    ),
    (2, 4, 146): "You two are done here. Abandon him and go home!",
    (2, 4, 147): "Meow! Abandon him, meow!",
    (2, 4, 148): "Meow! We're going home, meow!",
    (2, 4, 149): "Dorulumon!",
    (2, 4, 150): "...Cutemon!",
    (2, 4, 151): "Taking his friend hostage and forcing him to fight... That's despicable!",
    (2, 4, 152): (
        "So that's why you took Chibickmon! You planned to use him for something too!"
    ),
    (2, 4, 153): (
        "Ha-ha! That's a harsh joke, kid.\n"
        "This was an awful job; that was wonderful playtime!\n"
        "What could anyone possibly use such a cute child for?"
    ),
    (2, 4, 154): "Then why did you take him? What were you after?!",
    (2, 4, 155): (
        "Chibickmon and I were only playing.\n"
        "Kidnapping, exploiting, objectives... What are you even talking about?"
    ),
    (2, 4, 156): (
        "You're lying. You must've wanted to steal something...\n"
        "Though Chibickmon doesn't really have anything valuable. Uh... maybe something else..."
    ),
    (2, 4, 157): (
        "Insult Chibickmon again and I won't forgive you!\n"
        "Ugly faces really do hide ugly thoughts!\n"
        "Nothing is more precious than that child's cuteness, but nobody can ever steal it!\n"
        "You're filthy, unpleasant, absolutely awful! I refuse to share the same air!"
    ),
    (2, 4, 158): "What?! That makes no sense! Is she calling me ugly?!",
    (2, 4, 159): "Uh... of course not. Right, Shoutmon?",
    (2, 4, 160): (
        "Grr! That bizarre Minervamon called the future Digimon King ugly?!"
    ),
    (2, 4, 161): "You too...?",
    (2, 4, 162): "...Ah!",
    (2, 4, 163): "Part of Spadamon's abilities returned!",
    (2, 4, 164): "Spadamon, did you remember anything?",
    (2, 4, 165): (
        "About the Legendary Ancient Weapon ROG wants...\n"
        "Many armies and organizations came to this Zone searching for it long before ROG.\n"
        "But back then, a legendary warrior used the legendary weapon to protect the Zone...\n"
        "That's all. I can't remember any more."
    ),
    (2, 4, 166): "A legendary warrior who wielded the legendary weapon?!",
    (2, 4, 167): "Then they were this Zone's guardian?",
    (2, 4, 168): (
        "I feel like I know the legendary weapon. It has something to do with my memories..."
    ),
    (2, 4, 169): (
        "Taiki, Cutemon is safe and unhurt, but he's exhausted. Let's find somewhere to rest."
    ),
    (2, 4, 170): "All right. Let's return to Skyfort for now.",
    (2, 4, 171): (
        "Dorulumon! You seriously bit me back there! It's swelling up now! What do I do?!"
    ),
    (2, 4, 172): "It wasn't poisonous. Stop making a fuss over everything.",
    (2, 4, 173): "What's with that smug pretty-boy attitude?!",
    (2, 4, 174): (
        "Dorulumon really is grateful. He's just too stubborn to thank you honestly, kyu."
    ),
    (2, 4, 175): "Yeah, I know.",
    (2, 4, 176): "I'm glad Cutemon and the others returned safely.",
    (2, 4, 177): "Thank you so much! You really saved us, kyu!",
    (2, 4, 178): "Oh! Have you two settled things man-to-man?",
    (2, 4, 179): (
        "...Hmph. For now.\n"
        "From here on, I'll fight alongside Taiki's team. I'll be nearby, so talk to me whenever you need me."
    ),
    (2, 4, 180): "Then let's restart the Capacitor Tower in Spiral Amazon.",
    (2, 4, 181): "Yeah, let's do it.",
    (2, 4, 182): "Leave Skyfort to us!",
    (2, 4, 183): "We've gotten pretty friendly with the Digimon here too!",
    (2, 4, 184): "We're counting on you, Akari and Zenjirou.",
    (2, 4, 185): (
        "Dorulumon suffered because of me. Even if he heads out, I'll stay here with Akari and the others, kyu."
    ),
    (2, 4, 186): "All right, let's go!",
    (2, 4, 187): "No abnormalities, evil! No problems, evil!",
    (2, 4, 188): (
        "Those are ROG's grunt Digimon. They're guarding the area so tightly that we can't pass."
    ),
    (2, 4, 189): "Want to smash the gate and blast them away?",
    (2, 4, 190): (
        "Absolutely not! Then enemies would swarm us from both sides! No way!"
    ),
    (2, 4, 191): (
        "Yeah, getting spotted here would be bad. Let's find another way. Is there another path?"
    ),
    (2, 4, 192): "Hmm... Should we try entering the Digital Space ahead?",
})

# Batch 2H: global prose records 993-1070 (1,002 draft-English words).
# Pathfinder incident, Sparrowmon's distress call, and IceDevimon battle.
OVERRIDES.update({
    (2, 4, 193): "We can use the Pathfinder Device there.",
    (2, 4, 194): "The Path... what?",
    (2, 4, 195): (
        "It's a machine hidden only in our Skyfort.\n"
        "It creates passages called Paths that link even special spaces that normally can't be connected."
    ),
    (2, 4, 196): "I get it! That's why it's called the Path-something Device!",
    (2, 4, 197): "You understood that explanation?",
    (2, 4, 198): "Not at all!",
    (2, 4, 199): "F-for now, enter Digital Space through that Warp Portal.",
    (2, 5, 0): "Got it.",
    (2, 5, 1): "Linkage Path: Connect.",
    (2, 5, 2): "...Path connected.",
    (2, 5, 3): (
        "...Huh? That's Nene! And beside her... SkullKnightmon?!"
    ),
    (2, 5, 4): (
        "SkullKnightmon?! He's our enemy!\n"
        "Why is he with Nene? Is he threatening her with her brother as a hostage again?!"
    ),
    (2, 5, 5): (
        "Nene isn't that weak. To save her brother, she'd never submit to SkullKnightmon again."
    ),
    (2, 5, 6): (
        "T-Taiki! That machine the girl has is a Pathfinder Device--"
        "something that should exist only on Skyfort! Where did she get it?!"
    ),
    (2, 5, 7): "Destination input: Lost Space.",
    (2, 5, 8): "...Input: Lost Space. Locate the seal of the Legendary Ancient Weapon...",
    (2, 5, 9): (
        "The Legendary Ancient Weapon and Lost Space?!\n"
        "No! Taiki, stop her!\n"
        "ROG is desperately searching for Lost Space. It must be where the weapon is hidden!"
    ),
    (2, 5, 10): "What?! Is ROG controlling Nene?!",
    (2, 5, 11): "Nene! Snap out of it!",
    (2, 5, 12): "Eliminate all who obstruct the plan.",
    (2, 5, 13): "...Eliminate them all.",
    (2, 5, 14): (
        "G-g-g... Not... finished... Connect... to Lost Space... now..."
    ),
    (2, 5, 15): "...Link: Lost Space.",
    (2, 5, 16): "N-no! Stop!",
    (2, 5, 17): (
        "We... are ROG... We will obtain... everything... "
        "the legendary weapon... the legendary Digimon..."
    ),
    (2, 5, 18): (
        "Is that really SkullKnightmon? Taiki, something's wrong with him! This looks bad!"
    ),
    (2, 5, 19): "Spadamon, get back!",
    (2, 5, 20): (
        "Legendary weapon... legendary Digimon...\n"
        "I'm so close to remembering!\nBut we can't let ROG enter Lost Space!"
    ),
    (2, 5, 21): "Linkage rejected! Device overload!",
    (2, 5, 22): "...Connection denied. Energy detonation in five... four... three...",
    (2, 5, 23): "An explosion?! Taiki, Shoutmon, get down!",
    (2, 5, 24): "You've gotta be kidding!",
    (2, 5, 25): (
        "Someone... please help me!\n"
        "A dark, terrifying shadow won't let me go.\n"
        "I don't want to forget everyone. Don't tamper with my heart...\n"
        "Hurry... help me..."
    ),
    (2, 5, 26): "Sparrowmon!",
    (2, 5, 27): "You're awake, Taiki!",
    (2, 5, 28): (
        "I heard Sparrowmon asking me for help. Someone's holding her captive. We have to hurry!"
    ),
    (2, 5, 29): "...Where are we?",
    (2, 5, 30): "These are the Spiderweb Ruins.",
    (2, 5, 31): (
        "Spadamon and I were scouting the area.\n"
        "That Pathfinder explosion must've blown us here.\n"
        "Who knew Spadamon had power like that?"
    ),
    (2, 5, 32): (
        "I-I was desperate. I don't know how I did it.\n"
        "But it felt like the same power that surged through me when we activated the Capacitor Tower..."
    ),
    (2, 5, 33): "What happened after the explosion? Where's Nene?!",
    (2, 5, 34): "I don't know. But I don't think she reached Lost Space.",
    (2, 5, 35): (
        "Why are they searching for the Legendary Ancient Weapon?\n"
        "And Spadamon's power... Is it connected to the Capacitor Tower's administrator?"
    ),
    (2, 5, 36): (
        "I don't understand complicated stuff, but Spadamon is still Spadamon. Don't worry so much."
    ),
    (2, 5, 37): (
        "Oh, right. Sparrowmon is your friend, isn't she?\n"
        "If she's a prisoner, she may be at Skull Glacier ahead."
    ),
    (2, 5, 38): (
        "Why do you think she's at Skull Glacier? Wait... Sparrowmon hasn't become a skull, has she?!"
    ),
    (2, 5, 39): "Ha-ha... I don't think you need to worry about that.",
    (2, 5, 40): (
        "That's not what I meant! The ROG leader who controls Skull Glacier is terrifying.\n"
        "I would never go near him without you!"
    ),
    (2, 5, 41): (
        "A terrifying Digimon... I'm worried about Sparrowmon. Let's head to Skull Glacier now."
    ),
    (2, 5, 42): "I am IceDevimon, ROG's Freeze Leader--IceDevimon the Blizzard!",
    (2, 5, 43): "This is the terrifying Digimon? He looks kinda familiar.",
    (2, 5, 44): (
        "I saw someone like him in another Zone! I think a giant penguin froze him solid."
    ),
    (2, 5, 45): (
        "F-frozen solid?! No way! I wouldn't survive being frozen for even a second!"
    ),
    (2, 5, 46): "That spoiled Spadamon... Why does ROG want someone like him?",
    (2, 5, 47): "He apparently knows the legendary weapon's secret, devi.",
    (2, 5, 48): "And he can activate Towers that we couldn't, devi.",
    (2, 5, 49): "Hmm... So he has value. In that case...",
    (2, 5, 50): "Hey, IceDevimon! Where's Sparrowmon?!",
    (2, 5, 51): (
        "Sparrowmon? Ah, yes! The one with the long legs... tall and slender?\n"
        "Of course I know where that Sparrow-something is!\n"
        "If you want her location, hand over Spadamon!"
    ),
    (2, 5, 52): (
        "IceDevimon, that lie is terrible. Sparrowmon doesn't have legs!"
    ),
    (2, 5, 53): (
        "Wh-what?! Is that true?! Then I'll simply take him by force! Give me Spadamon!"
    ),
    (2, 5, 54): "Here he comes! Everyone, get ready!",
    (2, 5, 55): "Guh... So strong! How can mere children have such power?",
    (2, 5, 56): (
        "Taiki isn't just a kid! He's Xros Heart's General!\n"
        "We won't forgive an evil group like ROG!"
    ),
    (2, 5, 57): (
        "A group? ROG is no mere group. Soon you'll understand its true horror."
    ),
    (2, 5, 58): "Part of Spadamon's abilities returned!",
    (2, 5, 59): (
        "Taiki, I remember! The Legendary Ancient Weapon needs a warrior capable of wielding it.\n"
        "That warrior receives both the weapon and the Capacitor Towers.\n"
        "So the Tower administrator is that warrior!"
    ),
    (2, 5, 60): "Then is Spadamon the warrior because he can open the Towers?",
    (2, 5, 61): (
        "No, I don't think so. I can't open the doors whenever I want.\n"
        "The legendary warrior must still be somewhere out there!"
    ),
    (2, 5, 62): (
        "The legendary warrior and Spadamon... I feel like they're deeply connected."
    ),
    (2, 5, 63): (
        "But if that warrior controls the Towers, why aren't they fighting while the El Estou Zone is in danger?"
    ),
    (2, 5, 64): "There are still too many things we don't understand.",
    (2, 5, 65): "Obtained a key item!\nSpiderweb West Key",
    (2, 5, 66): (
        "That looks like the gate key for Spiderweb Ruins West.\n"
        "Remember where the Digital Space explosion dropped us? The west gate is right beside it."
    ),
    (2, 5, 67): "Could Sparrowmon be imprisoned there?!",
    (2, 5, 68): (
        "I think so. We have to save her quickly. Come on, you two!"
    ),
    (2, 5, 69): "...Nene?! What is she doing here alone?",
    (2, 5, 70): "Be careful, Taiki. Remember, ROG is controlling Nene.",
})

# Batch 2I: global prose records 1071-1141 (1,010 draft-English words).
# Sparrowmon rescue and first Pharaohmon encounter.
OVERRIDES.update({
    (2, 5, 71): "But something's wrong. She looks dazed...",
    (2, 5, 72): "Nene... Do you recognize us?",
    (2, 5, 73): "...A voice is calling.",
    (2, 5, 74): "Whose voice?",
    (2, 5, 75): (
        "Sparrowmon. She's trapped in darkness.\n"
        "While searching for me after I was blown away, the darkness of this world consumed her..."
    ),
    (2, 5, 76): "Nene, wait! If you're searching for Sparrowmon, come with us--",
    (2, 5, 77): (
        "...Sparrowmon is suffering nearby. I have to hurry. I have to save her..."
    ),
    (2, 5, 78): "Sparrowmon's voice? I heard it too! Nene must've heard the same thing.",
    (2, 5, 79): "She said Sparrowmon was close. How could she know that?",
    (2, 5, 80): "I don't know. But I feel it too. Sparrowmon is nearby.",
    (2, 5, 81): (
        "She was searching for Nene and became trapped in darkness? But who did that to her?"
    ),
    (2, 5, 82): "I'm worried about Nene, but we need to find Sparrowmon first!",
    (2, 5, 83): "Hee-hee. I've been waiting for you, Spadamon.",
    (2, 5, 84): (
        "I am Arukenimon, ROG's Poison Leader--Arukenimon the Predator!\n"
        "I knew Spadamon would come. Because this is what you boys want, isn't it?"
    ),
    (2, 5, 85): "Sparrowmon!",
    (2, 5, 86): "Sparrowmon! Thank goodness you're safe!",
    (2, 5, 87): (
        "How adorably innocent. But I'll erase those lovely smiles in a moment. Hee-hee!"
    ),
    (2, 5, 88): "Sparrowmon! Don't you recognize us?!",
    (2, 5, 89): "It's no use, Taiki. She's completely under their control.",
    (2, 5, 90): (
        "Hee-hee! Luring you boys here was easy.\n"
        "Your friend is under a powerful illusion cast by Lord ZDMillenniummon."
    ),
    (2, 5, 91): (
        "Lord ZDMillenniummon personally gave her to me as bait for Spadamon."
    ),
    (2, 5, 92): (
        "Her master now is the leader I adore--Lord ZDMillenniummon, ruler of ROG!"
    ),
    (2, 5, 93): "T-Taiki!",
    (2, 5, 94): (
        "It's okay, Spadamon.\n"
        "Sparrowmon, can you hear me? Remember us!\n"
        "You're too strong-willed and brave to be fooled by a trick like this!"
    ),
    (2, 5, 95): (
        "Useless! Hand over Spadamon!\n"
        "I will fulfill Lord ZDMillenniummon's dream of ruling the world with the Legendary Ancient Weapon!"
    ),
    (2, 5, 96): (
        "Tell that ZDMillenniummon this: we're Team Xros Heart!\n"
        "Our bonds burn hotter than anyone's. None of us will be fooled by a cheap trick!"
    ),
    (2, 5, 97): (
        "Hee-hee-hee! What a kindhearted fool.\n"
        "Taste the agony of being attacked by the friends you trust!"
    ),
    (2, 5, 98): (
        "N-no! How could I lose?! Spadamon... all of you... I'll never forgive this!"
    ),
    (2, 5, 99): "Part of Spadamon's abilities returned!",
    (2, 5, 100): "...Dynasmon.",
    (2, 5, 101): "What is it, Spadamon? Did you remember something?",
    (2, 5, 102): (
        "The legendary warrior who administers the Capacitor Towers was named Dynasmon.\n"
        "That's all I remember.\n"
        "Dynasmon... Wah! Why do I suddenly feel like a scary teacher is yelling at me?!"
    ),
    (2, 5, 103): "Do you remember Dynasmon scolding you?",
    (2, 5, 104): "Ugh... E-everyone?",
    (2, 5, 105): "Sparrowmon! Stay with us!",
    (2, 5, 106): "Sparrowmon!",
    (2, 5, 107): (
        "Huh? Taiki and Shoutmon... My head feels fuzzy. Why am I here?\n"
        "I was in the jungle when a strange voice called me...\n"
        "Oh! You two left me behind in that jungle! Stop doing that!\n"
        "I'm a member of Xros Heart too!"
    ),
    (2, 5, 108): "Wh-what? Did I say something strange?",
    (2, 5, 109): (
        "No, I'm happy, Sparrowmon! You're right. You're one of us!"
    ),
    (2, 5, 110): "Huh? Why say that all of a sudden? It's embarrassing!",
    (2, 5, 111): "I'm so glad, Sparrowmon! I'm happy too!",
    (2, 5, 112): (
        "Shoutmon, you're crying too? If this is about the jungle, you don't have to feel so bad."
    ),
    (2, 5, 113): (
        "You really don't remember. Rest for now.\n"
        "Akari, Zenjirou, and everyone else are at Skyfort. You'll be safe there."
    ),
    (2, 5, 114): (
        "This Gate Disc will take you straight there. Wait for us in the central room."
    ),
    (2, 5, 115): (
        "I still don't understand what's happening, but you're really happy I'm part of Xros Heart.\n"
        "I'm glad I joined! See you later!"
    ),
    (2, 5, 116): (
        "Sparrowmon really knows how to make us cry. Let's go activate the Capacitor Tower!"
    ),
    (2, 5, 117): "Taiki! Look...",
    (2, 5, 118): "Obtained a key item!\nSpiderweb East Key",
    (2, 5, 119): (
        "This opens the gate to Papyrus Desert. There should be another Capacitor Tower there."
    ),
    (2, 5, 120): "We need to activate every Tower. Let's head to the desert next.",
    (2, 5, 121): "Then let's go!",
    (2, 5, 122): "Ooooooh...!",
    (2, 5, 123): (
        "You have chosen my coffin well!\n"
        "I am Pharaohmon, ROG's Shining Leader--Pharaohmon the Grave!"
    ),
    (2, 5, 124): "Spadamon, this guy seems kinda funny.",
    (2, 5, 125): (
        "What?! He's a ROG leader! He's definitely going to demand me or try to steal me!"
    ),
    (2, 5, 126): (
        "Foolish Spadamon! I have no need of you!\n"
        "Calamity befalls all who oppose ROG!\n"
        "Whatever Lord ZDMillenniummon says, I shall bring great calamity upon you!"
    ),
    (2, 5, 127): "Here he comes, Taiki!",
    (2, 5, 128): "Taste calamity!",
    (2, 5, 129): (
        "Hmm... Why am I the one left in tatters? It seems the calamity befell me instead..."
    ),
    (2, 5, 130): "Um... excuse me.",
    (2, 5, 131): (
        "Silence! That didn't count! We shall start again from the beginning!"
    ),
    (2, 5, 132): "What did you say?",
    (2, 5, 133): (
        "First, I shall remove one stone blocking your path!\n"
        "You cannot advance until every stone is gone.\n"
        "If you wish to fight me, find me again! Fwahaha!"
    ),
    (2, 5, 134): "What's happening? An earthquake?",
    (2, 5, 135): "No... It feels like somewhere nearby is shaking.",
    (2, 5, 136): (
        "I remember. Pharaohmon is a terrifying Ruins Digimon who created the desert ruins.\n"
        "He can freely summon rocks from beneath the ground."
    ),
    (2, 5, 137): (
        "What?! Then we can't pass the rocks blocking the road unless we keep defeating him? What do we do?!"
    ),
    (2, 5, 138): "Calm down, Shoutmon. Panicking won't help.",
    (2, 5, 139): (
        "That 'blocking stone' was probably one of the tablets sealing the path.\n"
        "It disappeared, so a new route must be open!"
    ),
    (2, 5, 140): (
        "So we find and defeat Pharaohmon again? I'm worried he said he removed only one."
    ),
    (2, 5, 141): (
        "There are lots of identical coffins here. Don't open the wrong one!\n"
        "If a real ghost appears, I'll faint!"
    ),
})

# Batch 2J: global prose records 1142-1226 (1,000 draft-English words).
# Papyrus Desert coffin hunt and Pharaohmon rematches.
OVERRIDES.update({
    (2, 5, 142): (
        "There's no way to tell the coffins apart. But if we can beat Pharaohmon, "
        "we'll manage even when we open the wrong one. Let's go!"
    ),
    (2, 5, 143): (
        "Grave robbers who disturb our sleep receive a curse instead of treasure, mummy!"
    ),
    (2, 5, 144): "Grave robbers?",
    (2, 5, 145): "Suffer and learn the depth of your foolishness, mummy!",
    (2, 5, 146): "Wait, hold on!",
    (2, 5, 147): "I will not wait, mummy!",
    (2, 5, 148): (
        "Wait... You aren't grave robbers, mummy? How confusing!\n"
        "If you aren't, wear name tags saying so, mummy!"
    ),
    (2, 5, 149): "What?!",
    (2, 5, 150): (
        "Good moooorning, you boys! The one who shall face the bullets of my wrath is... you, mummy!"
    ),
    (2, 5, 151): "Wait, does 'mummy' mean you, or is it just how you talk?",
    (2, 5, 152): (
        "Why are you spouting nonsense, mummy?! The one defeated in this battle will naturally be... "
        "not me, but you, mummy!"
    ),
    (2, 5, 153): "...Which one is which?",
    (2, 5, 154): "Enough babbling! You're annoying me, mummy!",
    (2, 5, 155): (
        "If you think this defeated me, that's a big mistake, mummy! Remember me!"
    ),
    (2, 5, 156): "What a weird guy...",
    (2, 5, 157): "Fwahahahaha!",
    (2, 5, 158): (
        "You have chosen my coffin well! I am Pharaohmon, ROG's Shining Leader--Pharaohmon the Grave!"
    ),
    (2, 5, 159): "Uh... Didn't you already say that?",
    (2, 5, 160): (
        "Silence! Your circumstances are irrelevant. Great calamity shall befall you!"
    ),
    (2, 5, 161): "Guess we have to fight.",
    (2, 5, 162): "Insolent brats! I shall crush you!",
    (2, 5, 163): (
        "...Insolent little whelps... wielding troublesome tricks to return my calamity upon me..."
    ),
    (2, 5, 164): "That sounded like a tongue twister!",
    (2, 5, 165): (
        "It was not! Listen when others speak!\n"
        "I cannot accept losing to the likes of you! Absolutely unacceptable!"
    ),
    (2, 5, 166): "What?!",
    (2, 5, 167): "You're hiding again?!",
    (2, 5, 168): (
        "Silence! If you want me to surrender, find my coffin again! Fwahahaha!"
    ),
    (2, 5, 169): (
        "That sound and shaking... Another stone moved. A route must've opened somewhere."
    ),
    (2, 5, 170): "All right, Spadamon! On to the next one!",
    (2, 5, 171): "Spadamon, let's open the next coffin!",
    (2, 5, 172): (
        "Are you two treating this like a treasure hunt? We need to find Pharaohmon again!"
    ),
    (2, 5, 173): (
        "You're grave robbers, aren't you, mummy? No need to answer.\n"
        "From every possible angle, you can be nothing else, mummy!"
    ),
    (2, 5, 174): "W-wait, that's wrong, mummy!",
    (2, 5, 175): "Don't imitate me, mummy!",
    (2, 5, 176): (
        "Actually, let's just call you grave robbers, mummy. Look at that face--definitely a grave robber!"
    ),
    (2, 5, 177): "What? Does my face really look that scary, mummy?",
    (2, 5, 178): (
        "Our destined enemies! We have awaited this moment, mummy!\n"
        "Only a few who made enemies of the Mummymons have survived!"
    ),
    (2, 5, 179): "Only a few? And you admit that honestly?",
    (2, 5, 180): (
        "We have no pride worth protecting with dirty lies, mummy!\n"
        "You shall soon learn the pride of Mummymon!"
    ),
    (2, 5, 181): (
        "That was merely a tiny fraction of the countless Mummymons who happened to lose!\n"
        "Someday you'll understand our terror, mummy!"
    ),
    (2, 5, 182): "I think we understand it already...",
    (2, 5, 183): "Fwahahahaha!",
    (2, 5, 184): "You have chosen my coffin well!",
    (2, 5, 185): "Yes! We found Pharaohmon! We did it!",
    (2, 5, 186): (
        "Y-you're actually celebrating a battle with me?\n"
        "Someone as great as I am naturally attracts many pursuers. F-fwahahaha..."
    ),
    (2, 5, 187): "When he's that happy, fighting him feels kinda awkward.",
    (2, 5, 188): "Pharaohmon is strangely hard to hate.",
    (2, 5, 189): "You two! Stop taking it easy!",
    (2, 5, 190): (
        "Fwahahaha! Since you found me, I have no choice but to face you.\n"
        "Learn the horror of my calamity!"
    ),
    (2, 5, 191): (
        "Fwahaha! Don't relax yet. I have completely analyzed your power!"
    ),
    (2, 5, 192): "Okay, but isn't it about time to stop?",
    (2, 5, 193): "I'm exhausted, and I'm getting hungry.",
    (2, 5, 194): (
        "Y-your confidence ends here! Soon I shall obtain tremendous power.\n"
        "Then, without question, great calamity will truly befall you!"
    ),
    (2, 5, 195): "Is Pharaohmon just too embarrassed to quit now?",
    (2, 5, 196): "Taiki, don't say that! Pharaohmon will hear you!",
    (2, 5, 197): (
        "You shall bow before my reborn form! Fwahahahaha!"
    ),
    (2, 5, 198): "He escaped because you two were fooling around!",
    (2, 5, 199): (
        "Don't be mad, Spadamon. Sorry. We'll definitely catch him next time. Right, Taiki?"
    ),
    (2, 6, 0): (
        "Yeah. Even Pharaohmon must be getting weaker. We'll finish it next time. Let's go!"
    ),
    (2, 6, 1): "Sudden question, mummy: what's my best quality?",
    (2, 6, 2): "Uh... You'll never lack bandages if you get hurt!",
    (2, 6, 3): "Then it's useless until someone gets hurt, mummy!",
    (2, 6, 4): "Hmm. Bad answer...",
    (2, 6, 5): "Now is the time to use bandages on an injury, mummy...",
    (2, 6, 6): "What?! Are you hurt?",
    (2, 6, 7): "My heart is badly wounded! I need emergency surgery, mummy!",
    (2, 6, 8): "What does that even mean?!",
    (2, 6, 9): "Can you perform surgery on yourself?",
    (2, 6, 10): (
        "I don't know what you're sneaking around searching for, but too bad!\n"
        "The DigiShip you seek isn't here, mummy!"
    ),
    (2, 6, 11): "DigiShip? What are you talking about?",
    (2, 6, 12): "I appeared in the wrong place, mummy! Those goggles confused me!",
    (2, 6, 13): "Where were you trying to appear?!",
    (2, 6, 14): "Goggles like those mark a protagonist, mummy. Treasure them...",
    (2, 6, 15): "Seriously, where were you trying to appear?",
    (2, 6, 16): "As if I could tell you, mummy!",
    (2, 6, 17): "What a weird guy...",
    (2, 6, 18): "...That coffin is sitting in an obviously suspicious spot.",
    (2, 6, 19): "It's almost too easy to find. Is this a trap?",
    (2, 6, 20): "Look! He's coming out by himself!",
    (2, 6, 21): "Fwahahahaha!",
    (2, 6, 22): (
        "You have found my coffin! Indeed, I am Pharaohmon! But this time, that is not all!"
    ),
    (2, 6, 23): "What do you mean? You don't look any different.",
    (2, 6, 24): (
        "Fwahaha! Everything was meant to lure you here.\n"
        "Now behold my true power!"
    ),
    (2, 6, 25): "No longer Pharaohmon! Aaaaaaah!",
    (2, 6, 26): "Whaaaat?!",
})

# Batch 2K: global prose records 1227-1288 (1,007 draft-English words).
# Anubimon transformation, final desert clues, and Earthfort briefing.
OVERRIDES.update({
    (2, 6, 27): "...You're surprised too soon. Behold! Anubismon appears!",
    (2, 6, 28): "He transformed without DigiXros! What's going on?!",
    (2, 6, 29): (
        "It isn't DigiFusion or Jogress Up. This is Pharaohmon's--no, Anubismon's own power!"
    ),
    (2, 6, 30): (
        "You've mocked me long enough! This time I'll defeat you and seize everything!"
    ),
    (2, 6, 31): "He's serious this time! Everyone, be careful!",
    (2, 6, 32): (
        "Guh! How can this be?! I never imagined I could lose even after using Pyramid Power!"
    ),
    (2, 6, 33): (
        "Anubismon, tell us! How are the Legendary Ancient Weapon, the legendary warrior, "
        "and Spadamon connected?\n"
        "ROG may know something important that the amnesiac Spadamon doesn't!"
    ),
    (2, 6, 34): (
        "Until now, ROG pursued Spadamon under Lord ZDMillenniummon's orders to find the legendary weapon.\n"
        "But that era is over. ROG has already found the seal of the Legendary Ancient Weapon!\n"
        "ROG's glorious age begins now!"
    ),
    (2, 6, 35): "You found the Legendary Ancient Weapon's seal?",
    (2, 6, 36): "Part of Spadamon's abilities returned!",
    (2, 6, 37): "Well? Did you remember anything?!",
    (2, 6, 38): (
        "The legendary weapon's seal... Maybe activating every Capacitor System will reveal something.\n"
        "There are seven Capacitor Systems in all..."
    ),
    (2, 6, 39): "Seven? We've only visited six areas.",
    (2, 6, 40): "Huh? Maybe I'm mistaken. I thought there were seven.",
    (2, 6, 41): (
        "Spadamon, you're bad at counting! Don't worry. Just picture DigiNoir in your head--"
        "then you can count as high as you want!"
    ),
    (2, 6, 42): "Hey, something fell over there.",
    (2, 6, 43): "What key is that?",
    (2, 6, 44): (
        "It's for a gate in Spiral Amazon, near where we entered Digital Space.\n"
        "Papyrus Desert borders Spiral Amazon."
    ),
    (2, 6, 45): "So we circled all the way around and came back?",
    (2, 6, 46): (
        "Yeah. There must be six Towers after all.\n"
        "Activating every Capacitor Tower should reveal the seal's secret--"
        "and maybe all of my memories too."
    ),
    (2, 6, 47): (
        "Then we definitely can't ignore the Towers! Let's activate every one of them!"
    ),
    (2, 6, 48): (
        "Your choice is completely wrong, mummy! You face this lonely Mummymon!"
    ),
    (2, 6, 49): "...Oh, just another wrong coffin.",
    (2, 6, 50): (
        "Who are you calling wrong, mummy?! Don't underestimate Mummymon!\n"
        "I'll beat you black and blue!"
    ),
    (2, 6, 51): "But you're the one who called it the wrong choice.",
    (2, 6, 52): (
        "...Here too, I'm treated like the lowest grunt. Fine. Do whatever you want. Mock me all you like."
    ),
    (2, 6, 53): "That's where you're wrong, Mummymon.",
    (2, 6, 54): "I already know I'm the wrong one, mummy!",
    (2, 6, 55): (
        "No, that's not it. You aren't weak. You're one of the strongest opponents we've fought!"
    ),
    (2, 6, 56): (
        "Y-you can't fool me with compliments! R-remember this, mummy!"
    ),
    (2, 6, 57): "...Was he embarrassed?",
    (2, 6, 58): (
        "You touched a coffin in Papyrus Desert. That means you're picking a fight with Mummymon!"
    ),
    (2, 6, 59): (
        "Huh? We don't have business with Mummymon. It was just... an accident."
    ),
    (2, 6, 60): (
        "Why touch someone's coffin by accident, mummy?!\n"
        "If someone rang your doorbell and called it an accident, wouldn't you get mad?!"
    ),
    (2, 6, 61): "S-sorry!",
    (2, 6, 62): (
        "I remember your face! Mummymon never forgets a grudge until the grave!"
    ),
    (2, 6, 63): "Doesn't Mummymon already live in a grave?",
    (2, 6, 64): "See? Look at this place! Isn't it scary?",
    (2, 6, 65): (
        "You don't understand romance. This makes my sense of adventure burn!"
    ),
    (2, 6, 66): "Hmm... Still...",
    (2, 6, 67): "Akari! Zenjirou! Patamon! We're back! What was scary?",
    (2, 6, 68): "Isn't it scary when a machine nobody touched suddenly starts moving?",
    (2, 6, 69): "A gigantic machine coming to life? That's romantic!",
    (2, 6, 70): "What happened?",
    (2, 6, 71): (
        "Besides Skyfort, the El Estou Zone has an underground base called Earthfort.\n"
        "It had been stopped since ROG invaded, but it suddenly activated.\n"
        "I think starting the Capacitor Towers restored it."
    ),
    (2, 6, 72): (
        "Then we're finally getting a new base on the Energy Continent! Where is Earthfort?"
    ),
    (2, 6, 73): "Apparently it's at Crystal Volcano... and that place is terrifying!",
    (2, 6, 74): "C-Crystal Volcano?!",
    (2, 6, 75): "Zenjirou, why is that scary?",
    (2, 6, 76): (
        "Crystal Volcano is supposedly terrifying, and its wild Digimon are all powerful.\n"
        "But while Akari fears it, I feel the romance of a gigantic secret base coming online!"
    ),
    (2, 6, 77): "That's all you ever say! Taiki, do something about Zenjirou!",
    (2, 6, 78): (
        "We're locating Crystal Volcano's port now. Meanwhile, we need your help.\n"
        "More allied Digimon are returning, and their requests are reaching the Quest Monitor.\n"
        "Could you fulfill as many as possible?"
    ),
    (2, 6, 79): (
        "We're helping where we can, but they say leaving Skyfort is dangerous, so our options are limited."
    ),
    (2, 6, 80): (
        "Believe it or not, the Digimon are fighting over my attention. Being popular is tough!"
    ),
    (2, 6, 81): (
        "Zenjirou is a good playmate for the Pickmons. Apparently he's popular only with tiny children."
    ),
    (2, 6, 82): (
        "So requests requiring travel outside Skyfort must go to Taiki's team. Please help whenever you can."
    ),
    (2, 6, 83): (
        "Everyone on Skyfort is counting on you! Ask us if you need anything."
    ),
    (2, 6, 84): (
        "Request Quests, huh? You're popular, Taiki! Maybe you'll become the El Estou Zone's legendary warrior!"
    ),
    (2, 6, 85): (
        "Spadamon seems more suited to being a warrior than me. Right, Spadamon?"
    ),
    (2, 6, 86): "...Huh? What's wrong, Spadamon?",
    (2, 6, 87): (
        "N-nothing! Don't look at me!\n"
        "I heard Crystal Volcano is terrifying, but my legs definitely aren't shaking!"
    ),
    (2, 6, 88): (
        "Spadamon, is it really that scary? I'm excited to visit a new area!"
    ),
})

# Batch 2L: global prose records 1289-1364 (1,014 draft-English words).
# Crystal Volcano access, Kiriha's Lost Space attempt, and Spadamon's power.
OVERRIDES.update({
    (2, 6, 89): (
        "Yeah! It's actually a pretty beautiful place. And I heard the crystals there are sweet and delicious!"
    ),
    (2, 6, 90): (
        "Seriously?! I-I'm coming too! Wow, sweet crystals... I can't wait!"
    ),
    (2, 6, 91): (
        "Does he really love sweets that much? One day we'll see a Quest Monitor request from Spadamon saying, "
        "'Find me a delicious cake!'"
    ),
    (2, 6, 92): (
        "Nothing gets you motivated like something sweet! Anyway, please take care of everyone's Request Quests!"
    ),
    (2, 6, 93): "Taiki, Taiki! I've got huge news!",
    (2, 6, 94): "We found the port for Crystal Volcano!",
    (2, 6, 95): "Whoa! Nice work! You finally found it!",
    (2, 6, 96): "Ugh... They finally found it.",
    (2, 6, 97): (
        "But there seems to be a small problem. I need to explain the details, so could you come to the Central Room?"
    ),
    (2, 6, 98): "Guess it wasn't going to be that easy...",
    (2, 6, 99): "If it's come to this, I guess I have to prepare myself.",
    (2, 6, 100): "Come join us soon, Taiki!",
    (2, 6, 101): "So, is the flight squad finally assembled?",
    (2, 6, 102): "Yeah. Let's hear the full story in the Central Room.",
    (2, 6, 103): "I can't wait to fly through the sky!",
    (2, 6, 104): "Hey, Taiki! Hold up!",
    (2, 6, 105): (
        "First we should check the Capacitor Tower! I think we passed its entrance on the way here. "
        "Why don't you take a look?"
    ),
    (2, 6, 106): (
        "Let's see... Of the places we've visited, Armadillomon near the mountains by Skyfort should work. "
        "The Tyrannomon around here ought to be able to dig too."
    ),
    (2, 6, 107): "Are you sure this is the right thing to do?",
    (2, 6, 108): (
        "...Enough, MailBirdramon. There is no other way."
    ),
    (2, 6, 109): "...Huh? Are those two Kiriha and MailBirdramon?",
    (2, 6, 110): (
        "Why is Kiriha in a place like this? He didn't follow us just because he's Taiki's rival, did he?"
    ),
    (2, 6, 111): "He seems to be holding something... What is that, some kind of machine?",
    (2, 6, 112): (
        "T-Taiki! That machine he's holding is a Pathfinder Device! Those only exist aboard Skyfort! "
        "H-how?! Where did he get one?!"
    ),
    (2, 6, 113): "Kiriha, it appears we have company after all.",
    (2, 6, 114): (
        "Taiki's arrival is within our projections. Hurry, MailBirdramon. We're finding the Legendary Ancient Weapon. "
        "Linkage Path, connect! Destination input: Lost Space!"
    ),
    (2, 6, 115): (
        "The Legendary Ancient Weapon... and Lost Space? N-no! Taiki, stop him! "
        "ROG has been desperately searching for Lost Space! It must be where the Legendary Ancient Weapon is hidden!"
    ),
    (2, 6, 116): "W-what?! Why is Kiriha trying to reach a place like that?!",
    (2, 6, 117): "Stop, Kiriha! You'll lead ROG straight to it!",
    (2, 6, 118): (
        "We eliminate anything that interferes with the plan--even Xros Heart. Is that your order, Kiriha?"
    ),
    (2, 6, 119): (
        "...My order stands. No one will get in our way. We are the blue flame--Team Blue Flare! Do it, MailBirdramon!"
    ),
    (2, 6, 120): "Kiriha... H-hurry... Make the connection...",
    (2, 6, 121): (
        "...Sorry, Taiki. There is no other way. Linkage Path, connect! Destination input: Lost Space!"
    ),
    (2, 6, 122): "N-no! Stop!",
    (2, 6, 123): "The legendary Digimon... I have to... find it...",
    (2, 6, 124): "Taiki, get back! Something's wrong!",
    (2, 6, 125): "Spadamon! Get away from there!",
    (2, 6, 126): (
        "The legendary weapon... the legendary Digimon... I'm so close to remembering! "
        "But I can't let them enter Lost Space!"
    ),
    (2, 6, 127): "Linkage rejected! Device overload!",
    (2, 6, 128): "What?! The connection was rejected?! The energy is going to explode!",
    (2, 6, 129): "E-explode?! Taiki, Shoutmon, get down!",
    (2, 6, 130): "You've gotta be kidding me...!",
    (2, 6, 131): (
        "Someone... please help me! A black, terrifying shadow won't let me go. "
        "I don't want to forget everyone... Don't tamper with my heart... Please... help..."
    ),
    (2, 6, 132): "Sparrowmon...!",
    (2, 6, 133): "You're awake, Taiki!",
    (2, 6, 134): (
        "I heard Sparrowmon calling for help. Someone has her captive. We have to save her, fast!"
    ),
    (2, 6, 135): "...Where are we?",
    (2, 6, 136): "These are the Spiderweb Ruins.",
    (2, 6, 137): (
        "Spadamon and I were just scouting the area! Looks like the Pathfinder explosion sent us flying here. "
        "I never knew Spadamon had that kind of power!"
    ),
    (2, 6, 138): (
        "Y-yeah. I was desperate back there. I don't know how I did it, but I felt the same power welling up "
        "inside me as when I activated the Capacitor Tower. Why...?"
    ),
    (2, 6, 139): (
        "What happened after the explosion? Where are Kiriha and the others?"
    ),
    (2, 6, 140): "...I don't know. But I don't think they made it into Lost Space.",
    (2, 6, 141): (
        "I see... But why are they searching for the Legendary Ancient Weapon? And Spadamon's power... "
        "Could he be connected to the Capacitor Towers' administrator?"
    ),
    (2, 6, 142): (
        "I don't get all that complicated stuff, Spadamon, but you're still you. Don't let it get to you."
    ),
    (2, 6, 143): (
        "Yeah... Come to think of it, Sparrowmon is one of your friends, right? "
        "If she was captured, maybe she's somewhere ahead at Skull Glacier."
    ),
    (2, 6, 144): (
        "Why do you think she's being held at Skull Glacier? Wait... You don't mean Sparrowmon has already become a skull?!"
    ),
    (2, 6, 145): "Ahaha... I don't think we need to worry about that.",
    (2, 6, 146): (
        "That's not what I mean! The ROG leader who controls Skull Glacier is supposed to be terrifying. "
        "I wouldn't go anywhere near it without you guys!"
    ),
    (2, 6, 147): (
        "A terrifying Digimon... I'm worried about Sparrowmon. Shoutmon, Spadamon--let's head to Skull Glacier now."
    ),
    (2, 6, 148): "...Is that Kiriha? What's he doing here alone?",
    (2, 6, 149): (
        "Looks like he's searching for something. Be careful, Taiki. He might attack without warning!"
    ),
    (2, 6, 150): (
        "But he isn't really your enemy, is he? Maybe you can work something out if you talk to him."
    ),
    (2, 6, 151): (
        "Kiriha, what are you doing? Why are you searching for the Legendary Ancient Weapon?"
    ),
    (2, 6, 152): (
        "Taiki... Trying to stop me is pointless. I will have it, no matter what."
    ),
    (2, 6, 153): "Have what--the legendary weapon?",
    (2, 6, 154): "This has nothing to do with you. Stay out of it.",
    (2, 6, 155): (
        "Wait, Kiriha! Why are you so obsessed with this? If there's a reason, tell us."
    ),
    (2, 6, 156): "...What I want is the power to change everything.",
    (2, 6, 157): "The power to change everything...?",
    (2, 6, 158): (
        "I always thought he was a cool customer, but isn't he getting even harder to approach?"
    ),
    (2, 6, 159): "Still... he looked like he was in pain.",
    (2, 6, 160): (
        "For now, shouldn't we search for Sparrowmon? She may be somewhere nearby."
    ),
    (2, 6, 161): (
        "Yeah. Sparrowmon comes first. But we can't just leave Kiriha like this, either."
    ),
    (2, 6, 162): (
        "Hououmon surveyed the area from the sky. It looks like things around Earthfort have gotten really bad."
    ),
    (2, 6, 163): "What do you mean?",
    (2, 6, 164): (
        "Earthfort is inside Crystal Volcano--and ROG's leader Digimon are gathering there in force!"
    ),
})

# Batch 2M: global prose records 1365-1438 (exactly 1,000 draft-English words).
# The assault on Earthfort and the ROG leaders' sacrifices.
OVERRIDES.update({
    (2, 6, 165): "Why are they all gathering there...?",
    (2, 6, 166): (
        "It looks like Earthfort is being controlled by ROG's supreme commander, ZDMillenniummon! "
        "The leader Digimon are guarding the fort, so they must have assembled on his orders."
    ),
    (2, 6, 167): "So he's the evil mastermind! All right, let's storm the place!",
    (2, 6, 168): (
        "But something doesn't add up. If they wanted to stay hidden, they wouldn't gather so openly in one place! "
        "This has to be a trap meant to capture Spadamon!"
    ),
    (2, 6, 169): (
        "You're right. Charging into enemy territory now is dangerous. We should investigate more thoroughly first..."
    ),
    (2, 6, 170): "No. We go now.",
    (2, 6, 171): (
        "Remember what Anubismon said in Papyrus Desert? ROG found the seal on the Legendary Ancient Weapon. "
        "If that's true, won't they try to break the seal immediately?"
    ),
    (2, 6, 172): "You think the seal is inside Earthfort?",
    (2, 6, 173): (
        "What?! I-is it really? We can't let ROG break that seal! We have to stop them!"
    ),
    (2, 6, 174): (
        "...Spadamon really has grown. He's so much braver than when we first met him. "
        "We need to find a way to help too! Cutemon, let's hold a strategy meeting in the Commander Room."
    ),
    (2, 6, 175): "H-hey, wait! Don't leave me out!",
    (2, 6, 176): (
        "Crystal Volcano, here we come! Let's go, Taiki! There's no way we'll let ROG use the Legendary Ancient Weapon!"
    ),
    (2, 6, 177): "Right! Let's move!",
    (2, 6, 178): "Be careful. They're waiting for you.",
    (2, 6, 179): (
        "Thanks, Hououmon. Then we'd better make sure we're completely prepared."
    ),
    (2, 6, 180): "Oh, come on...",
    (2, 6, 181): "That's the guy who occupied Skyfort!",
    (2, 6, 182): (
        "Just like the flight squad reported... ROG's leader Digimon are protecting ZDMillenniummon."
    ),
    (2, 6, 183): (
        "W-we have to reach Earthfort fast, or ROG will take the legendary weapon!"
    ),
    (2, 6, 184): "...I never imagined you pests would still be alive!",
    (2, 6, 185): "Stop making everyone in this Zone suffer!",
    (2, 6, 186): "We're taking the El Estou Zone back!",
    (2, 6, 187): (
        "Still as insolent as ever... But I have nowhere left to retreat. You will not pass!"
    ),
    (2, 6, 188): "...Grrrraaaaaah!",
    (2, 6, 189): "What's happening...?",
    (2, 6, 190): "Lord ZDMillenniummon! Now, turn me into your power!",
    (2, 6, 191): "W-what's going on?! What happened to him?",
    (2, 6, 192): (
        "We are ROG! We will use any means necessary to seize everything--even if that means sacrificing ourselves!"
    ),
    (2, 6, 193): "W-what did he say...?!",
    (2, 6, 194): "H-hey... What is that thing...?",
    (2, 6, 195): (
        "Yes, Minotaurmon... I desire your power. If your destiny is to scatter into digital dust, then become one with me..."
    ),
    (2, 6, 196): "Now I'll be reborn as part of the strongest Digimon!",
    (2, 6, 197): "W-what just happened...? Did it eat Minotaurmon?",
    (2, 6, 198): (
        "Many of the bosses we've fought grew stronger by absorbing their subordinates. "
        "Could that shadow really be ZDMillenniummon?!"
    ),
    (2, 6, 199): "...There's a good chance. We can't let our guard down.",
    (2, 7, 0): "Puku-ku-ku! We meet again!",
    (2, 7, 1): "You! You're the one we met at Knuckle Coast!",
    (2, 7, 2): (
        "ROG's Splash Leader, Pukumon the Prickle, will teach you the difference between our abilities!"
    ),
    (2, 7, 3): (
        "Pukumon, stop this! If you keep fighting, the black shadow will absorb you too!"
    ),
    (2, 7, 4): (
        "You people truly are amusing! Did you think someone as clever as me hadn't noticed the shadow? Puku-ku-ku!"
    ),
    (2, 7, 5): "Then why are you doing this...?",
    (2, 7, 6): (
        "All of ROG shall be gathered into that shadow! Puku-ku-ku! And for that purpose, your existence is an obstacle!"
    ),
    (2, 7, 7): "...Puku-ku-ku! That one actually hurt a little.",
    (2, 7, 8): "Just give up!",
    (2, 7, 9): (
        "You still don't understand why I'm here. Did you think I was fighting blindly? "
        "I've already reported everything about the way you battle."
    ),
    (2, 7, 10): "Well done, Pukumon...",
    (2, 7, 11): "Now surrender your wisdom to me...",
    (2, 7, 12): "As you command, our emperor of darkness. Puku-ku-ku!",
    (2, 7, 13): "What is wrong with ROG...? Aren't they afraid of disappearing?",
    (2, 7, 14): "Any boss who sacrifices his own allies is worthless!",
    (2, 7, 15): (
        "Minotaurmon gave him 'power,' and Pukumon gave him 'wisdom'... What did that shadow mean?"
    ),
    (2, 7, 16): "...Maybe those qualities are keys to breaking the seal.",
    (2, 7, 17): (
        "Pukumon said he reported how we fight. The enemies ahead are bound to be even stronger!"
    ),
    (2, 7, 18): "Doesn't matter who we face--we won't lose! Let's keep moving!",
    (2, 7, 19): "Hi again, you guys! We meet once moooore!",
    (2, 7, 20): (
        "You! You're the one who kidnapped Chibickmon! And you had the nerve to hold Dorulumon and Cutemon hostage!"
    ),
    (2, 7, 21): "Still calling it a kidnapping? How rude, you ugly little thing!",
    (2, 7, 22): "Who are you calling ugly?! Grrr, you make me so mad!",
    (2, 7, 23): "Minervamon... Answer me.",
    (2, 7, 24): (
        "If you love cute things, you could live peacefully with everyone without invading the Zone. "
        "Why take it in a way that makes everyone suffer?"
    ),
    (2, 7, 25): (
        "Minervamon... If you like cute things, you might even get along with Akari. "
        "Chibickmon likes you too. I just can't believe you're truly evil."
    ),
    (2, 7, 26): (
        "You're all ugly, but you say the sweetest things! I don't exactly hate dreamy little fools, you know?"
    ),
    (2, 7, 27): "...What did you say?!",
    (2, 7, 28): (
        "Everybody has things they gotta do, whether they wanna or not. You can't live on wishes alone! "
        "Maybe your reality is sweet, but my life is bitter, heavy, dirty, and dark! "
        "That's why I can appreciate cute things. You understand?"
    ),
    (2, 7, 29): "Minervamon!",
    (2, 7, 30): "If you won't come to me, then I'm coming to you!",
    (2, 7, 31): (
        "Ow-ow-ow... Good job, you guys! You beat me a little bit! Heehee... Ahahahaha!"
    ),
    (2, 7, 32): (
        "How can you keep laughing like that?! There's something seriously wrong with you!"
    ),
    (2, 7, 33): "Ha! That's totally true! Of course I'm messed up! So what? Got a problem?",
    (2, 7, 34): (
        "Taiki, there's no way Minervamon is good! She's just mocking us and having fun!"
    ),
    (2, 7, 35): "It's a rule of Team Cute!",
    (2, 7, 36): (
        "When you're down, laugh! When life gets rough, laugh even harder! "
        "That's the promise I made with the precious friends I lost in battle. "
        "Watching you reminds me of those days..."
    ),
    (2, 7, 37): (
        "Minervamon, have you grown fond of this boy? No matter. I shall take the data of your agility."
    ),
    (2, 7, 38): (
        "...That was our original deal, right? Fine. Go ahead and take it."
    ),
})

# Batch 2N: global prose records 1439-1517 (1,003 draft-English words).
# ROG's remaining leaders, the Omega Area, and Nene's possession.
OVERRIDES.update({
    (2, 7, 39): (
        "There is nothing to fear. With you at the center, all your allies will become a single being."
    ),
    (2, 7, 40): (
        "The Legendary Ancient Weapon... Collecting all this data for something like that? "
        "ROG is way crazier than I am! Someday these ugly kids will take you down!"
    ),
    (2, 7, 41): "Yeeeeah-hoooo!",
    (2, 7, 42): "...What was her deal...?",
    (2, 7, 43): (
        "She called us ugly right to the end... Dang it, Taiki! I don't know why, but this really hurts."
    ),
    (2, 7, 44): (
        "Yeah, Shoutmon. I feel it too. We won't let that monster do whatever it wants anymore!"
    ),
    (2, 7, 45): (
        "I am IceDevimon, ROG's Freeze Leader--IceDevimon the Blizzard!"
    ),
    (2, 7, 46): (
        "He's the boss of Skull Glacier! Watch out--he's a liar! He tried using Sparrowmon as a hostage "
        "when he hadn't even captured her!"
    ),
    (2, 7, 47): (
        "Ah... I should have thought of that. F-fwahaha! You fools don't know that ROG has captured Sparrowmon! "
        "If you want her returned, admit defeat immediately!"
    ),
    (2, 7, 48): (
        "...You're the one who doesn't know. We already rescued Sparrowmon, and she's doing just fine!"
    ),
    (2, 7, 49): "W-whaaaat?! Is that true?!",
    (2, 7, 50): "Grr! Then I'll simply crush you with force!",
    (2, 7, 51): "Guh... How could I lose to these brats...?!",
    (2, 7, 52): (
        "IceDevimon! Lies won't get you anywhere. Until you understand that, you can never beat us!"
    ),
    (2, 7, 53): "F-fwahahahaha! Are you sure about that?",
    (2, 7, 54): "What do you mean?!",
    (2, 7, 55): "Lies and deceit... They can become power too!",
    (2, 7, 56): (
        "Exactly. Just as light casts a shadow, shining strength requires darkness..."
    ),
    (2, 7, 57): "I-I really will be reborn as the strongest, won't I...?",
    (2, 7, 58): (
        "Yes. The data of your 'cunning' is essential to the new being. Everything must converge upon the Omega Area."
    ),
    (2, 7, 59): "A-ah... Ahahaha! E-e-evolve?!",
    (2, 7, 60): "The Omega Area...? What does that mean?",
    (2, 7, 61): "Will we learn everything if we reach Earthfort...?",
    (2, 7, 62): (
        "Taiki! Shoutmon! Hurry to Earthfort! 'Omega Area'... Something about that name feels terribly wrong."
    ),
    (2, 7, 63): (
        "Wrong how? Does it feel like getting chewed out by your teacher again?"
    ),
    (2, 7, 64): (
        "...I don't know. When I remembered the name Dynasmon, my heart felt warm. "
        "But 'Omega Area' feels terrifying and unknowable. The name makes my heart turn cold..."
    ),
    (2, 7, 65): (
        "Then the key to Spadamon's memories must be there too. Let's hurry to Earthfort!"
    ),
    (2, 7, 66): "Heehee! You boys finally made it this far.",
    (2, 7, 67): (
        "Arukenimon! I'll never forgive you for controlling Sparrowmon!"
    ),
    (2, 7, 68): (
        "She was a precious gift from Lord ZDMillenniummon... I haven't forgotten that humiliation!"
    ),
    (2, 7, 69): "Don't talk about our friend like she's an object!",
    (2, 7, 70): "Heehee! Is that what you call a burning friendship?",
    (2, 7, 71): (
        "Ugh, how sickening. If that garbage data must be used, it's better off serving Lord ZDMillenniummon. "
        "She was under mind control anyway. She couldn't feel a thing."
    ),
    (2, 7, 72): "Arukenimon... You're horrible!",
    (2, 7, 73): (
        "You boys will be my next gift to the boss. Would pink ribbons look nice on your mangled bodies? "
        "Oh, I can hardly wait! I'll put you out of your misery!"
    ),
    (2, 7, 74): (
        "You... I'll never forgive you! Never, never, never! I-I-I'll never forgive you!"
    ),
    (2, 7, 75): "S-she's terrifying...",
    (2, 7, 76): (
        "ROG, the legendary weapon--I'll offer everything to Lord ZDMillenniummon!"
    ),
    (2, 7, 77): "H-hey, Arukenimon...!",
    (2, 7, 78): (
        "No matter how often we crush it, the El Estou Zone rises again! Curse that Dynasmon...!"
    ),
    (2, 7, 79): "Dynasmon?! You know that name?",
    (2, 7, 80): (
        "Heeheehee! Oh, I know! I know exactly why Spadamon lost his memories!"
    ),
    (2, 7, 81): "What?!",
    (2, 7, 82): "The reason is--!",
    (2, 7, 83): (
        "Arukenimon, I value your cruelty, but your loose tongue is your greatest flaw..."
    ),
    (2, 7, 84): "N-no, stop...!",
    (2, 7, 85): (
        "Damn you, ZDMillenniummon! He erased her just to keep her quiet!"
    ),
    (2, 7, 86): (
        "Dynasmon was the legendary warrior who wielded the Legendary Ancient Weapon and managed the Capacitor Towers. "
        "Is he connected to my memories...?"
    ),
    (2, 7, 87): (
        "The Legendary Ancient Weapon... Dynasmon, who can wield it... my memories... and the Omega Area. "
        "I don't understand. But I know we can't let them break the weapon's seal! Hurry to Earthfort!"
    ),
    (2, 7, 88): (
        "I never expected to face you again! I need no introduction. I am Pharaohmon, ROG's Shining Leader--"
        "Pharaohmon the Grave!"
    ),
    (2, 7, 89): "Huh? Aren't you Anubismon?",
    (2, 7, 90): "Maybe he needs a pyramid to transform.",
    (2, 7, 91): "Then this'll be easy!",
    (2, 7, 92): (
        "How pitiful that you never realized I was holding back! Now I'll show you my true power--and a great calamity!"
    ),
    (2, 7, 93): (
        "Grrr! How humiliating! Why can I never defeat a pack of nameless brats, no matter how often we fight?!"
    ),
    (2, 7, 94): (
        "Our name is Team Xros Heart! We just can't abandon people suffering right in front of us!"
    ),
    (2, 7, 95): "Xros Heart... A name like a blazing heart itself...",
    (2, 7, 96): "...Ah, yes. I haven't truly lost yet.",
    (2, 7, 97): (
        "Exactly, Pharaohmon. This is only the beginning. Become one with us, and you will know no fear, doubt, "
        "or suffering. Now give me your 'tenacity.'"
    ),
    (2, 7, 98): (
        "Very well... Take everything! Crush us into pieces and remake us as the ultimate being!"
    ),
    (2, 7, 99): (
        "Team Xros Heart! We will rise again, and when we do, we will crush you without fail!"
    ),
    (2, 7, 100): "Taiki! Spadamon!",
    (2, 7, 101): "How many ROG leaders are left?",
    (2, 7, 102): "L-let's see... That should be every one of ROG's leader Digimon!",
    (2, 7, 103): (
        "Yeah... Although there's still one more... No, never mind. Get to Earthfort and stop them from breaking the seal!"
    ),
    (2, 7, 104): "Hey, Taiki... Isn't that Nene?!",
    (2, 7, 105): "So ROG is still controlling her...",
    (2, 7, 106): (
        "Listen, Nene! We found Sparrowmon, the partner you searched for all this time. "
        "She's with us now, waiting for you to come back."
    ),
    (2, 7, 107): "...Sparrowmon? Who...? I don't know her...",
    (2, 7, 108): "Nene forgot Sparrowmon...?!",
    (2, 7, 109): (
        "...No. That can't be true. Nene could never forget Sparrowmon... I refuse to believe it!"
    ),
    (2, 7, 110): "Foolish, pitiful creature. Trust only in yourself...",
    (2, 7, 111): "Taiki! Get back!",
    (2, 7, 112): "Damn it! Was this a trap?!",
    (2, 7, 113): "Nene! Remember Sparrowmon! Remember us!",
    (2, 7, 114): (
        "G-gagagaga... As expected... You are the boy who tamed Spadamon..."
    ),
    (2, 7, 115): "This one... has already served its purpose... Gagaga...",
    (2, 7, 116): (
        "Lost Space... I already made them find it... I alone am the strongest... Everything will be mine..."
    ),
    (2, 7, 117): (
        "What was going on with them? It was like a completely different person had taken over."
    ),
})

# Batch 2O: global prose records 1518-1599 (1,002 draft-English words).
# Nene's rescue, the Weapon Digimon truth, and Barbamon's reveal.
OVERRIDES.update({
    (2, 7, 118): "So they used Nene to find Lost Space...?",
    (2, 7, 119): "Nene! Can you hear me?! Wake up!",
    (2, 7, 120): "Nene!",
    (2, 7, 121): "Hey, Nene! Are you okay?!",
    (2, 7, 122): (
        "...Taiki? I... Sparrowmon! Where is Sparrowmon?!"
    ),
    (2, 7, 123): (
        "She's safe! Don't worry, Nene. Sparrowmon is with us!"
    ),
    (2, 7, 124): (
        "Oh... thank goodness! I heard Sparrowmon's voice in the darkness the whole time, but I couldn't move. "
        "A terrifying darkness held me captive and wouldn't let go..."
    ),
    (2, 7, 125): (
        "Those SkullKnightmon who were with you acted strangely. Were they being controlled too?"
    ),
    (2, 7, 126): (
        "...No. That SkullKnightmon was a fake ZDMillenniummon created from my memories."
    ),
    (2, 7, 127): "He made a fake from your memories?! Is that even possible?",
    (2, 7, 128): (
        "Taiki, this is serious! ZDMillenniummon is entering Lost Space to carry out some plan. "
        "I think he intends to revive the Weapon Digimon!"
    ),
    (2, 7, 129): "The Weapon Digimon? Not the legendary weapon...?",
    (2, 7, 130): "...Are you Spadamon?",
    (2, 7, 131): "Huh?! Y-yeah, I am... Why?",
    (2, 7, 132): (
        "So you're the one... We have to protect you. Taiki, don't let him join the next battle! "
        "You absolutely cannot take him!"
    ),
    (2, 7, 133): (
        "Is Nene still confused? Why is she so worried about Spadamon...?"
    ),
    (2, 7, 134): "We can figure that out later. First, let's help Nene...",
    (2, 7, 135): "Nene?! Where are you going?",
    (2, 7, 136): (
        "This is bad! Earthfort is up ahead! She went alone to stop them from breaking the seal!"
    ),
    (2, 7, 137): (
        "Whoa, whoa! She charged straight toward ZDMillenniummon without preparing? She really is still confused!"
    ),
    (2, 7, 138): "After her!",
    (2, 7, 139): "Nene, are you okay?! ...Who are those guys?",
    (2, 7, 140): (
        "Now... connect to Lost Space... Break the seal... The legendary weapon... "
        "the legendary Digimon... They will be mine."
    ),
    (2, 7, 141): (
        "Hey, Lord ZDMillenniummon... Don't you think this is weird? You suddenly talk like a machine, "
        "mutter nonsense, and try breaking the seal without telling your leaders. Are you okay?"
    ),
    (2, 7, 142): (
        "It's Lord ZDMillenniummon. I'm sure it's fine. Once he has the legendary weapon, ROG will rule everything. "
        "Then all our hard work will finally pay off."
    ),
    (2, 7, 143): "So that's ZDMillenniummon...",
    (2, 7, 144): "ZDMillenniummon is about to break the seal!",
    (2, 7, 145): "We made it just in time!",
    (2, 7, 146): "Taiki! Why did you bring Spadamon here?!",
    (2, 7, 147): (
        "Spadamon is one of us. We couldn't leave him behind alone. And if your friends were in danger, "
        "you'd come save them even if they told you not to, right?"
    ),
    (2, 7, 148): (
        "...You're right. That's who you are. When I was suffering, you reached out to help me..."
    ),
    (2, 7, 149): "Don't carry this alone. Tell us what you know.",
    (2, 7, 150): (
        "ROG's objective is to revive the Legendary Ancient Weapon here in the El Estou Zone."
    ),
    (2, 7, 151): (
        "We know that! ZDMillenniummon is trying to break the seal in Earthfort, right? "
        "So where exactly is this legendary weapon?"
    ),
    (2, 7, 152): (
        "The Legendary Ancient Weapon isn't an ordinary weapon. It's a Weapon Digimon that transforms into the ultimate weapon."
    ),
    (2, 7, 153): "A Weapon Digimon?! A Digimon can become a weapon?!",
    (2, 7, 154): (
        "Yes. That's the El Estou Zone's secret. Whoever possesses the Weapon Digimon could destroy the world, "
        "which is why this Zone is constantly targeted. Dynasmon once protected the Zone beside it. "
        "But where Dynasmon went and why the Weapon Digimon was sealed remain mysteries."
    ),
    (2, 7, 155): "The Weapon Digimon...",
    (2, 7, 156): "Taiki, we're out of time. For now, we have to stop ZDMillenniummon!",
    (2, 7, 157): (
        "All right, let's go, Taiki and Spadamon! It's finally time for our last showdown with ROG!"
    ),
    (2, 7, 158): "We absolutely cannot lose!",
    (2, 7, 159): "Hey! Shoutmon! Spadamon!",
    (2, 7, 160): "Huh?! A-a pose? W-wait! Um... What do I do?!",
    (2, 7, 161): "Before they notice us! Three... two... one... Go!",
    (2, 7, 162): "Wait! You guys! Choco-manderrr!",
    (2, 7, 163): "...Spadamon, you really flubbed that line.",
    (2, 7, 164): "And what does 'Choco-mander' even mean...?",
    (2, 7, 165): "...How far were you trying to count?",
    (2, 7, 166): "G-gagaga... S-s-s-Spadamon...!",
    (2, 7, 167): "Here it comes! We're counting on you, Taiki!",
    (2, 7, 168): "Spadamon... Xros Heart... Delete!",
    (2, 7, 169): (
        "ROG is finished! Give up on breaking the Weapon Digimon's seal!"
    ),
    (2, 7, 170): "G-gagagaga... Spa... Spada... mon...",
    (2, 7, 171): "What happened? Did the shock break him?",
    (2, 7, 172): "Whaaat?! Why is that shadow here when he's standing right there?!",
    (2, 7, 173): (
        "Then the shadow that erased every leader Digimon wasn't ZDMillenniummon after all...?!"
    ),
    (2, 7, 174): "Then what is that shadow?!",
    (2, 7, 175): (
        "G-gagagaga... Spa... Spadamon... The legendary Digimon... will be mine!"
    ),
    (2, 7, 176): (
        "Completely broken already? I thought it would last longer. No matter. With this creature's data of 'hatred,' "
        "I finally have everything I need..."
    ),
    (2, 7, 177): "It absorbed ZDMillenniummon too?!",
    (2, 7, 178): "What in the world is that thing?",
    (2, 7, 179): (
        "Everything is assembled. Now I need only find the Omega Area in Lost Space. Then Armamon will belong to me..."
    ),
    (2, 7, 180): "Who are you?!",
    (2, 7, 181): "...Kudou Taiki, General of Xros Heart.",
    (2, 7, 182): (
        "In a sense, I owe my progress to you. As your reward, I shall reveal my true form..."
    ),
    (2, 7, 183): "That's Barbamon?!",
    (2, 7, 184): "You know him, Nene?",
    (2, 7, 185): (
        "He's a vicious Digimon who'll use any means to achieve his goals. Of course... Now it all makes sense!"
    ),
    (2, 7, 186): "What is it, Nene?",
    (2, 7, 187): (
        "Creating SkullKnightmon and DeadlyAxemon, controlling Sparrowmon and me... "
        "Barbamon's illusion techniques explain all of it!"
    ),
    (2, 7, 188): (
        "Money isn't the only kind of treasure, you ignorant fools!"
    ),
    (2, 7, 189): (
        "Why are you yelling at me?! You're the one who went berserk whenever anything valuable appeared!"
    ),
    (2, 7, 190): "Don't complain to us! Tell that to yourself!",
    (2, 7, 191): (
        "Ah, that was an entertaining show. Watching you desperately struggle to recover your friends, "
        "I could barely keep myself from laughing."
    ),
    (2, 7, 192): (
        "Shut up, Barbamon! We won't let you do whatever you want, and you won't break Earthfort's seal!"
    ),
    (2, 7, 193): (
        "You misunderstand. Earthfort is merely a box used to gather ROG. The true seal lies within Lost Space--"
        "the Omega Area, where the legendary Weapon Digimon Armamon will be revived. "
        "I created ROG to obtain them both!"
    ),
    (2, 7, 194): (
        "Barbamon! What are you plotting? Why would you tell us all that?!"
    ),
    (2, 7, 195): "Consider it a parting gift before you die.",
    (2, 7, 196): "Everyone, get back! He's planning something--",
    (2, 7, 197): "T-Taiki?!",
    (2, 7, 198): "Wait, Barbamon!",
    (2, 7, 199): (
        "Well, well... Amano Nene, the General who abandoned her former team and submitted to Xros Heart. "
        "You were deceived by such a simple illusion. Do you really think you can stop me?"
    ),
})

# Batch 2P: global prose records 1600-1677 (1,015 draft-English words).
# Barbamon's escape and the Kiriha-route Earthfort sequence.
OVERRIDES.update({
    (2, 8, 0): (
        "You performed admirably. You even served as excellent bait, luring Spadamon and the others into activating "
        "every Capacitor Tower."
    ),
    (2, 8, 1): "M-my body... I can't move...",
    (2, 8, 2): (
        "But you know too much. To keep you from giving Spadamon any information, I'll send you somewhere "
        "you can never return from! Without that knowledge, Spadamon can do nothing."
    ),
    (2, 8, 3): "Nene... R-run...!",
    (2, 8, 4): (
        "Even if you cast me away, Xros Heart won't disappear! Everyone in this Zone believes in Taiki and Spadamon. "
        "Their feelings are Xros Heart itself!"
    ),
    (2, 8, 5): "Silence, little girl!",
    (2, 8, 6): "Nene!",
    (2, 8, 7): (
        "Stop whining, weakling General. I merely sent her to another Zone. Perhaps you'll meet again someday--"
        "assuming she isn't torn apart in transit."
    ),
    (2, 8, 8): "Barbamon... I'll never forgive you!",
    (2, 8, 9): (
        "Hmm... There is nothing more you can do, yet you still struggle. I think I'll enjoy this comedy a little longer."
    ),
    (2, 8, 10): "We won't lose... We can't lose!",
    (2, 8, 11): "Tell the Weapon Digimon to run while it still can!",
    (2, 8, 12): (
        "Parrotmon surveyed the area from the sky. It looks like things around Earthfort have gotten really bad."
    ),
    (2, 8, 13): "What do you mean?",
    (2, 8, 14): (
        "Earthfort is inside Crystal Volcano--and ROG's leader Digimon are gathering there in force!"
    ),
    (2, 8, 15): "Why are they all gathering there...?",
    (2, 8, 16): (
        "It looks like Earthfort is being controlled by ROG's supreme commander, ZDMillenniummon! "
        "The leader Digimon are guarding the fort, so they must have assembled on his orders."
    ),
    (2, 8, 17): "So he's the evil mastermind! All right, let's storm the place!",
    (2, 8, 18): (
        "But something doesn't add up. If they wanted to stay hidden, they wouldn't gather so openly in one place! "
        "This has to be a trap meant to capture Spadamon!"
    ),
    (2, 8, 19): (
        "You're right. Charging into enemy territory now is dangerous. We should investigate more thoroughly first..."
    ),
    (2, 8, 20): "No. We go now.",
    (2, 8, 21): (
        "Remember what Anubismon said in Papyrus Desert? ROG found the seal on the Legendary Ancient Weapon. "
        "If that's true, won't they try to break the seal immediately?"
    ),
    (2, 8, 22): "You think the seal is inside Earthfort?",
    (2, 8, 23): (
        "What?! I-is it really? We can't let ROG break that seal!"
    ),
    (2, 8, 24): (
        "...Spadamon really has grown. He's so much braver than when we first met him. "
        "We need to find a way to help too! Cutemon, let's hold a strategy meeting in the Commander Room."
    ),
    (2, 8, 25): "H-hey, wait! Don't leave me out!",
    (2, 8, 26): (
        "Crystal Volcano, here we come! Let's go, Taiki! There's no way we'll let ROG use the Legendary Ancient Weapon!"
    ),
    (2, 8, 27): "Right! Let's move!",
    (2, 8, 28): "Be careful. They're waiting for you.",
    (2, 8, 29): (
        "Thanks, Parrotmon. Then we'd better make sure we're completely prepared."
    ),
    (2, 8, 30): "Hey, Taiki... Isn't that Kiriha?",
    (2, 8, 31): (
        "Yeah, but something's wrong with him. I still can't just leave him like this."
    ),
    (2, 8, 32): (
        "Kiriha... What happened? I can feel something dark inside you."
    ),
    (2, 8, 33): "...I... I must overcome my sorrow.",
    (2, 8, 34): "What's wrong with Kiriha? He looks completely dazed.",
    (2, 8, 35): "...I don't know. But that isn't the Kiriha we know.",
    (2, 8, 36): "Grrrraaaaah! Xros Heart... destroy...",
    (2, 8, 37): "Taiki! Get back!",
    (2, 8, 38): (
        "Something's wrong with them! It's like somebody is controlling them!"
    ),
    (2, 8, 39): (
        "Kiriha, what happened?! Where is the blue flame in your heart? Wake up!"
    ),
    (2, 8, 40): "Grrrraaaah...!",
    (2, 8, 41): "Kiriha... W-what happened to me...?",
    (2, 8, 42): (
        "Guh... My head feels like it's splitting open. Let me return to the Xros Loader for a while..."
    ),
    (2, 8, 43): "...Did they come back to their senses?",
    (2, 8, 44): (
        "Like Sparrowmon when we rescued her from the Spiderweb Ruins... Was somebody controlling them?"
    ),
    (2, 8, 45): "Kiriha! Can you hear me?! Do you recognize me?!",
    (2, 8, 46): "Kiriha!",
    (2, 8, 47): "What happened?! Who did this to you?",
    (2, 8, 48): "Ugh... Taiki? What have I been doing...?",
    (2, 8, 49): "Someone was controlling you! Who was it?!",
    (2, 8, 50): "...So that's what happened. The black shadow took control of me...",
    (2, 8, 51): (
        "That black shadow... Is it the thing that devoured ROG's leader Digimon?"
    ),
    (2, 8, 52): (
        "Yes. The shadow appeared before me and offered an alliance to obtain the Legendary Ancient Weapon."
    ),
    (2, 8, 53): "You didn't actually join ROG, did you?!",
    (2, 8, 54): (
        "Don't insult me! I submit to no one. I was investigating ROG's activity in this Zone. "
        "They are likely trying to revive the Weapon Digimon, and we must prevent that at any cost."
    ),
    (2, 8, 55): "The Weapon Digimon? Not the legendary weapon...?",
    (2, 8, 56): "...So you're Spadamon.",
    (2, 8, 57): "Huh?! Y-yeah, I am... Why?",
    (2, 8, 58): (
        "...You must become stronger, so you can recover what was taken from you."
    ),
    (2, 8, 59): "Taiki! How does Kiriha know about Spadamon?!",
    (2, 8, 60): "Calm down, Shoutmon. First we need to hear him out...",
    (2, 8, 61): "Wait, Kiriha! Where are you going?",
    (2, 8, 62): (
        "This is bad! Earthfort is up ahead! He went alone to stop them from breaking the seal!"
    ),
    (2, 8, 63): (
        "Whoa, whoa! He charged straight toward ZDMillenniummon without preparing? Even for Kiriha, that's reckless!"
    ),
    (2, 8, 64): "After him!",
    (2, 8, 65): "Kiriha, are you okay?! ...Who are those guys?",
    (2, 8, 66): (
        "Now... connect to Lost Space... Break the seal... The legendary weapon... "
        "the legendary Digimon... They will be mine."
    ),
    (2, 8, 67): (
        "Hey, Lord ZDMillenniummon... Don't you think this is weird? You suddenly talk like a machine, "
        "mutter nonsense, and try breaking the seal without telling your leaders. Are you okay?"
    ),
    (2, 8, 68): (
        "It's Lord ZDMillenniummon. I'm sure it's fine. Once he has the legendary weapon, ROG will rule everything. "
        "Then all our hard work will finally pay off."
    ),
    (2, 8, 69): "So that's ZDMillenniummon...",
    (2, 8, 70): "ZDMillenniummon is about to break the seal!",
    (2, 8, 71): "We made it just in time!",
    (2, 8, 72): "Taiki, stay out of this! I have a score to settle with him.",
    (2, 8, 73): (
        "Calm down, Kiriha! This isn't like you. We need a plan, and your Digimon are still exhausted from the last battle."
    ),
    (2, 8, 74): (
        "...You're right. I let myself get too worked up. I never expected you to be the one to remind me."
    ),
    (2, 8, 75): "Tell us what you know.",
    (2, 8, 76): (
        "ROG's objective is to revive the Legendary Ancient Weapon here in the El Estou Zone."
    ),
    (2, 8, 77): (
        "We know that! ZDMillenniummon is trying to break the seal in Earthfort, right? "
        "So where exactly is this legendary weapon?"
    ),
})

# Batch 2Q: global prose records 1678-1752 (1,001 draft-English words).
# Kiriha-route Barbamon reveal, exile, and Skyfort's occupation.
OVERRIDES.update({
    (2, 8, 78): (
        "The Legendary Ancient Weapon isn't an ordinary weapon. It's a Weapon Digimon that transforms into the ultimate weapon."
    ),
    (2, 8, 79): "A Weapon Digimon?! A Digimon can become a weapon?!",
    (2, 8, 80): (
        "Yes. That's the El Estou Zone's secret. Whoever possesses the Weapon Digimon could destroy the world, "
        "which is why this Zone is constantly targeted. Dynasmon once protected the Zone beside it. "
        "But where Dynasmon went and why the Weapon Digimon was sealed remain mysteries."
    ),
    (2, 8, 81): "The Weapon Digimon...",
    (2, 8, 82): (
        "Taiki, there's no time! My Digimon collapsed after that last battle. I need your strength to stop ZDMillenniummon."
    ),
    (2, 8, 83): (
        "All right, let's go, Taiki and Spadamon! It's finally time for our last showdown with ROG!"
    ),
    (2, 8, 84): "We absolutely cannot lose!",
    (2, 8, 85): "Hey! Shoutmon! Spadamon!",
    (2, 8, 86): "Huh?! A-a pose? W-wait! Um... What do I do?!",
    (2, 8, 87): "Before they notice us! Three... two... one... Go!",
    (2, 8, 88): "Wait! You guys! Choco-manderrr!",
    (2, 8, 89): "...Spadamon, you really flubbed that line.",
    (2, 8, 90): "And what does 'Choco-mander' even mean...?",
    (2, 8, 91): "...How far were you trying to count?",
    (2, 8, 92): "G-gagaga... S-s-s-Spadamon...!",
    (2, 8, 93): "Here it comes! We're counting on you, Taiki!",
    (2, 8, 94): "Spadamon... Xros Heart... Delete!",
    (2, 8, 95): "ROG is finished! Give up on breaking the Weapon Digimon's seal!",
    (2, 8, 96): "G-gagagaga... Spa... Spada... mon...",
    (2, 8, 97): "What happened? Did the shock break him?",
    (2, 8, 98): "Whaaat?! Why is that shadow here when he's standing right there?!",
    (2, 8, 99): (
        "Then the shadow that erased every leader Digimon wasn't ZDMillenniummon after all...?!"
    ),
    (2, 8, 100): "Then what is that shadow?!",
    (2, 8, 101): (
        "G-gagagaga... Spa... Spadamon... The legendary Digimon... will be mine!"
    ),
    (2, 8, 102): (
        "Completely broken already? I thought it would last longer. No matter. With this creature's data of 'hatred,' "
        "I finally have everything I need..."
    ),
    (2, 8, 103): "It absorbed ZDMillenniummon too?!",
    (2, 8, 104): "What in the world is that thing?",
    (2, 8, 105): (
        "Everything is assembled. Now I need only find the Omega Area in Lost Space. Then Armamon will belong to me..."
    ),
    (2, 8, 106): "Who are you?!",
    (2, 8, 107): (
        "...Kudou Taiki, General of Xros Heart. And Aonuma Kiriha, General of Blue Flare."
    ),
    (2, 8, 108): (
        "In a sense, I owe my progress to you. As your reward, I shall reveal my true form..."
    ),
    (2, 8, 109): "...B-Barbamon?!",
    (2, 8, 110): "You know him, Kiriha?",
    (2, 8, 111): (
        "He's a vicious Digimon who'll use any means to achieve his goals. Of course... Now it all makes sense!"
    ),
    (2, 8, 112): "What makes sense, Kiriha?",
    (2, 8, 113): (
        "Damn it! So Barbamon's illusion technique was what made me lose control of myself!"
    ),
    (2, 8, 114): "Money isn't the only kind of treasure, you ignorant fools!",
    (2, 8, 115): (
        "Why are you yelling at me?! You're the one who went berserk whenever anything valuable appeared!"
    ),
    (2, 8, 116): "Don't complain to us! Tell that to yourself!",
    (2, 8, 117): (
        "Team Blue Flare... Ensnaring you took some effort, but you still fell so easily. What a disappointment."
    ),
    (2, 8, 118): (
        "Shut up, Barbamon! We won't let you do whatever you want, and you won't break Earthfort's seal!"
    ),
    (2, 8, 119): (
        "You misunderstand. Earthfort is merely a box used to gather ROG. The true seal lies within Lost Space--"
        "the Omega Area, where the legendary Weapon Digimon Armamon will be revived. "
        "I created ROG to obtain them both!"
    ),
    (2, 8, 120): "Barbamon! What are you plotting? Why would you tell us all that?!",
    (2, 8, 121): "Consider it a parting gift before you die.",
    (2, 8, 122): "Everyone, get back! He's planning something--",
    (2, 8, 123): "T-Taiki?!",
    (2, 8, 124): "Wait, Barbamon! Fight me!",
    (2, 8, 125): (
        "Well, Aonuma Kiriha... You still have the strength to fight? But you're merely a man unable to abandon his past. "
        "Do you really think you can stop me?"
    ),
    (2, 8, 126): (
        "You performed admirably. You even served as excellent bait, luring Spadamon and the others into activating "
        "every Capacitor Tower."
    ),
    (2, 8, 127): "M-my body... I can't move...",
    (2, 8, 128): (
        "But you know too much. To keep you from giving Spadamon any information, I'll send you somewhere "
        "you can never return from! Without that knowledge, Spadamon can do nothing."
    ),
    (2, 8, 129): "Kiriha... R-run...!",
    (2, 8, 130): (
        "Do whatever you want. I will never submit! One day I'll change this entire world with my own power. "
        "But for now, I entrust everything to Taiki and Xros Heart!"
    ),
    (2, 8, 131): "Silence, you insolent brat!",
    (2, 8, 132): "Kiriha!",
    (2, 8, 133): (
        "Stop whining, weakling General. I merely sent him to another Zone. Perhaps you'll meet again someday--"
        "assuming he isn't torn apart in transit."
    ),
    (2, 8, 134): "Barbamon... I'll never forgive you!",
    (2, 8, 135): (
        "Hmm... There is nothing more you can do, yet you still struggle. I think I'll enjoy this comedy a little longer."
    ),
    (2, 8, 136): "We won't lose... We can't lose!",
    (2, 8, 137): "Tell the Weapon Digimon to run while it still can!",
    (2, 8, 138): "Taiki! Are you okay?!",
    (2, 8, 139): "...Shoutmon? Y-yeah. I think I'm all right.",
    (2, 8, 140): (
        "I thought lightning struck right in front of me... Then everything went dark, and I must have passed out. "
        "What happened to Barbamon and that girl afterward?"
    ),
    (2, 8, 141): (
        "Barbamon sent Nene to another Zone. Damn it... I couldn't do anything to stop him!"
    ),
    (2, 8, 142): (
        "It isn't only your fault, Taiki. I couldn't do anything either. Barbamon deliberately spared us. "
        "He was mocking us!"
    ),
    (2, 8, 143): (
        "We need to contact Patamon and the others. Barbamon may be heading for Skyfort..."
    ),
    (2, 8, 144): "There you are! Everyone, this is terrible!",
    (2, 8, 145): "Hououmon! Thank goodness the Digimon flight squad is safe!",
    (2, 8, 146): (
        "We're not safe at all! ROG invaded the City, forced everyone out, and occupied the Tower. "
        "Skyfort is surrounded by a crackling barrier, so we can't even get close!"
    ),
    (2, 8, 147): (
        "What?! Zenjirou, Akari, and everyone else are still aboard Skyfort!"
    ),
    (2, 8, 148): (
        "That crackling barrier must be the Protection Field. It's a powerful shield designed to defend Skyfort..."
    ),
    (2, 8, 149): "Then they're safe! Patamon must have activated the barrier, right?",
    (2, 8, 150): (
        "But the Protection Field only works when every Capacitor Tower is set to Emergency Mode. "
        "If the Towers have been occupied, then..."
    ),
    (2, 8, 151): "Barbamon has taken control of Skyfort!",
    (2, 8, 152): "Is this really the time to stand around babbling about that?",
})

# Batch 2R: global prose records 1753-1832 (1,011 draft-English words).
# DarkKnightmon's alliance and the first Shadow Guard towers.
OVERRIDES.update({
    (2, 8, 153): (
        "Do you know why this happened? Because you people are hopelessly incompetent."
    ),
    (2, 8, 154): "SkullKnightmon?! DeadlyAxemon too... Are you the real ones?",
    (2, 8, 155): (
        "Of course we are. What are you talking about? Neither you nor this Zone has any time left."
    ),
    (2, 8, 156): (
        "If Barbamon is the shadow controlling ROG, then his Shadow Guards have seized the Capacitor Towers. "
        "You could say this Zone already belongs to him."
    ),
    (2, 8, 157): "Why are SkullKnightmon and DeadlyAxemon in this Zone?",
    (2, 8, 158): (
        "We were drawn here by the dark power of Armamon, the Weapon Digimon. Nothing more."
    ),
    (2, 8, 159): "The Digimon Barbamon is trying to revive...",
    (2, 8, 160): "Come on! You expect us to trust that story?!",
    (2, 8, 161): (
        "Believe whatever you wish. But what if I said we can investigate the Zone where Nene was sent?"
    ),
    (2, 8, 162): "...What did you say?!",
    (2, 8, 163): (
        "You need only cooperate with us while we search for Nene. It's hardly a bad offer."
    ),
    (2, 8, 164): "...You can really find where Nene went?",
    (2, 8, 165): (
        "I don't expect your trust, and I won't explain my reasons. But Barbamon has been using our names without permission. "
        "That has left us rather displeased."
    ),
    (2, 8, 166): "If you don't want our help, that's no concern of ours.",
    (2, 8, 167): "...All right. SkullKnightmon, lend us your strength.",
    (2, 8, 168): "T-Taiki?!",
    (2, 8, 169): (
        "SkullKnightmon and DeadlyAxemon once traveled with Nene. We have no other lead, so we'll have to trust them."
    ),
    (2, 8, 170): (
        "A wise decision. We'll wait in this area. Speak to us whenever you require assistance."
    ),
    (2, 8, 171): (
        "Oh, right! I brought Penmon from the Item Shop. There's also an Airport ahead, and Tentomon installed "
        "DigiLab and DigiFarm PCs inside the tent. I'll support you however I can, so ask me if you need anything. "
        "Good luck, everyone!"
    ),
    (2, 8, 172): (
        "Taiki, Shoutmon, can I tell you something? It's about getting back into Skyfort..."
    ),
    (2, 8, 173): "You know how?",
    (2, 8, 174): (
        "The Protection Field appears when every Capacitor Tower enters Emergency Mode. "
        "If we return all the Towers to Normal Mode, we should be able to reach Skyfort!"
    ),
    (2, 8, 175): "So we need to revisit every Tower we activated...",
    (2, 8, 176): (
        "If Barbamon releases Armamon, he could control this Zone--no, the entire Digital World. "
        "We don't know what might happen to your world either."
    ),
    (2, 8, 177): "The Weapon Digimon is really that powerful...?",
    (2, 8, 178): (
        "Spadamon still hasn't recovered all his memories. I wish we at least knew what Armamon is like "
        "and why it was sealed."
    ),
    (2, 8, 179): "And I wish I could remember Dynasmon too...",
    (2, 8, 180): "Anyway, retaking the Capacitor Towers is our top priority!",
    (2, 8, 181): (
        "Barbamon's Shadow Guards must be incredibly strong. We should check the DigiLab and DigiFarm inside the tent. "
        "Come on, you two!"
    ),
    (2, 8, 182): "...That's strange. There isn't a Shadow Guard here.",
    (2, 8, 183): "Hiii!",
    (2, 8, 184): (
        "Oh, a little kid who got left behind? Are you okay? What are you doing here?"
    ),
    (2, 8, 185): "Is she lost? We need to evacuate her quickly...",
    (2, 8, 186): "Great, just what we needed right now...",
    (2, 8, 187): (
        "Hide nearby for a little while. Someone scary might show up."
    ),
    (2, 8, 188): (
        "It's okay! Don't worry. We'll take you somewhere safe, I promise!"
    ),
    (2, 8, 189): (
        "Thanks! You guys are nice. But I was told to wait here and never let anyone touch the Capacitor System. "
        "That's the game we're playing!"
    ),
    (2, 8, 190): "Hey, we don't have time to play with you...",
    (2, 8, 191): (
        "The red one is worth 500 points, the blue one 800... and the boy with goggles is worth 10,000. Right?"
    ),
    (2, 8, 192): "...Wait. You don't mean...",
    (2, 8, 193): "Are you the new toys Lord Barbamon told me about?",
    (2, 8, 194): "...You've gotta be kidding.",
    (2, 8, 195): (
        "I'm Lalamon, the Lovely Elite of Barbamon's Shadow Guard, sent to protect this Capacitor Tower!"
    ),
    (2, 8, 196): "S-she tricked us! Be careful, Taiki!",
    (2, 8, 197): "Right! Let's go, everyone!",
    (2, 8, 198): "How about that, Lalamon? Now move aside!",
    (2, 8, 199): (
        "Aww, I lost. Time for me to disappear. Someone this weak can't protect Lord Barbamon."
    ),
    (2, 9, 0): "W-wait! What do you mean, disappear? Where are you going?",
    (2, 9, 1): (
        "Isn't it obvious? Lord Barbamon will absorb me! The more Shadow Guards you defeat, "
        "the stronger he becomes. Isn't that wonderful?"
    ),
    (2, 9, 2): "Bye-bye!",
    (2, 9, 3): (
        "She says 'bye-bye' like it's nothing! Every one of them throws their life away so easily..."
    ),
    (2, 9, 4): "...",
    (2, 9, 5): "What's wrong, Spadamon?",
    (2, 9, 6): (
        "...My body's getting warmer, and I'm starting to feel a little sleepy."
    ),
    (2, 9, 7): "I'll switch the Tower back to Normal Mode for now.",
    (2, 9, 8): "Switched to Normal Mode!",
    (2, 9, 9): (
        "This Tower's energy is no longer being supplied to the Protection Field."
    ),
    (2, 9, 10): "All right! On to the next one!",
    (2, 9, 11): "Be careful. That must be the Shadow Guard.",
    (2, 9, 12): (
        "Hahahaha! You have done well to reach me, chosen heroes! I am the ancient Digital Hazard Dragon, "
        "sent to protect this Capacitor Tower--Megidramon, Blast Elite of Barbamon's Shadow Guard!"
    ),
    (2, 9, 13): "Doesn't his personality clash with his appearance...?",
    (2, 9, 14): "Y-yeah. He caught me off guard.",
    (2, 9, 15): "Hey, what's this about us being chosen heroes?",
    (2, 9, 16): (
        "Maybe it's because he's a dragon. You see that kind of thing in games all the time..."
    ),
    (2, 9, 17): (
        "Barbamon thinks this is a game?! What a joke! Let's go, Taiki--blow that guy away!"
    ),
    (2, 9, 18): "Come, chosen heroes!",
    (2, 9, 19): (
        "Hahahaha! To defeat the mighty Megidramon, you truly are the chosen ancient hazard heroes of the dragon!"
    ),
    (2, 9, 20): "That doesn't make any sense!",
    (2, 9, 21): (
        "His strength exhausted, our hero falls before achieving his dream! But Megidramon sought still greater power, "
        "and so the dark emperor, Lord Barbamon, absorbed him! Hahahaha!"
    ),
    (2, 9, 22): "...Damn it. What is wrong with these guys?",
    (2, 9, 23): (
        "Barbamon enjoys watching us fight. Fine--we'll charge straight into his trap!"
    ),
    (2, 9, 24): "Spadamon, switch the Tower to Normal Mode.",
    (2, 9, 25): "Okay.",
    (2, 9, 26): "Switched to Normal Mode!",
    (2, 9, 27): "What's wrong, Spadamon?",
    (2, 9, 28): "I want something sweet...",
    (2, 9, 29): "Where did that come from?!",
    (2, 9, 30): (
        "Spadamon, are you okay? Is operating the Towers draining your strength?"
    ),
    (2, 9, 31): (
        "Yeah, I'm starting to feel dazed... But I'm okay. Let's keep going."
    ),
    (2, 9, 32): (
        "Well, well! The famous boys have arrived! Yes, come closer! Come to me!"
    ),
})

# Batch 2S: global prose records 1833-1941 (1,001 draft-English words).
# TigerVespamon, MarineDevimon, and RookChessmon Shadow Guards.
OVERRIDES.update({
    (2, 9, 33): "Mmm... Give it to me!",
    (2, 9, 34): "...What is her deal? Is she really a Shadow Guard?",
    (2, 9, 35): "Why would Barbamon pick someone this weird...?",
    (2, 9, 36): "He's completely toying with us...",
    (2, 9, 37): "Damn it! Does he think this is a game?!",
    (2, 9, 38): (
        "I'm TigerVespamon, the Speedy Elite of Barbamon's Shadow Guard, sent to protect this Capacitor Tower! "
        "You can shorten it to TG Vespamon--but call me Tigress!"
    ),
    (2, 9, 39): "No way!",
    (2, 9, 40): "Mmm... Give it to me!",
    (2, 9, 41): "Ugh, she's really creeping me out...",
    (2, 9, 42): (
        "What's wrong, shy boys? Okay, here's a special offer. You can call me Tiggy!"
    ),
    (2, 9, 43): "No way!",
    (2, 9, 44): "Who would call you that?!",
    (2, 9, 45): "Absolutely not!",
    (2, 9, 46): "Mmm... Give it to me!",
    (2, 9, 47): "We're not losing to this clown! Take her down, Taiki!",
    (2, 9, 48): (
        "My, aren't we impatient? Fine, then! I'll hit you so hard, all that hate will turn into love!"
    ),
    (2, 9, 49): "...That was a rough battle.",
    (2, 9, 50): "...Think she'll calm down now?",
    (2, 9, 51): (
        "Hey, TG Vespamon! Tell Barbamon that if he keeps playing games, he's going to get hurt!"
    ),
    (2, 9, 52): "Yeah! We absolutely won't lose!",
    (2, 9, 53): (
        "Why do you hate me so much? Lord Barbamon is the only one who accepts and understands me. "
        "Wait for me, my lord! I'm coming to become one with you!"
    ),
    (2, 9, 54): "Pretty sure he isn't interested in you at all.",
    (2, 9, 55): "Mmm... Give it to meee!",
    (2, 9, 56): "Shoutmon... Did you have to be that blunt?",
    (2, 9, 57): "Yeah... That might've been a little too blunt.",
    (2, 9, 58): "It's fine! You have to be firm with someone like her!",
    (2, 9, 59): "I'll go switch the Tower's mode.",
    (2, 9, 60): "Switched to Normal Mode!",
    (2, 9, 61): "Spadamon, are you okay? You look exhausted.",
    (2, 9, 62): "Y-yeah... I don't know why, but my body feels hot.",
    (2, 9, 63): "Don't tell me you're coming down with a cold.",
    (2, 9, 64): "Don't push yourself until you collapse. Overdoing it is dangerous!",
    (2, 9, 65): "That's rich coming from you, Taiki... Come on, let's go!",
    (2, 9, 66): "...Urp.",
    (2, 9, 67): "What's wrong, Spadamon?",
    (2, 9, 68): "S-sorry, everyone... Wait a second. That Shadow Guard... Urp.",
    (2, 9, 69): "Hey, what happened?! Did it attack you somehow?!",
    (2, 9, 70): "N-no, it's not... anything. I-I'm fi--blech!",
    (2, 9, 71): "That 'blech' didn't sound fine at all! What's wrong, Spadamon?",
    (2, 9, 72): "...This is embarrassing, but I can't stand anything squid-like.",
    (2, 9, 73): "Come to think of it, I've heard squid is bad for cats.",
    (2, 9, 74): "...I'm not a cat.",
    (2, 9, 75): (
        "Nothing we can do about it. Spadamon, hold your nose! Taiki, let's finish this fast!"
    ),
    (2, 9, 76): "So you pests are the ones I've heard whispering insults!",
    (2, 9, 77): (
        "I am MarineDevimon, the Wet Elite of Barbamon's Shadow Guard, sent to protect this Capacitor Tower!"
    ),
    (2, 9, 78): (
        "Blech! I-I can't handle this! He's gross and shiny, and he smells horribly fishy. "
        "I haven't felt this defeated in ages..."
    ),
    (2, 9, 79): "Are you okay? I told you to hold your nose!",
    (2, 9, 80): (
        "I see! Lord Barbamon predicted this reaction. Still, even with the advantage, this feels deeply insulting!"
    ),
    (2, 9, 81): "I-I won't let Barbamon have his way! Urgh... Urp!",
    (2, 9, 82): "Why would you say that right to his face?!",
    (2, 9, 83): "I'll crush you until that nose stops working!",
    (2, 9, 84): "Yeah... At this point...",
    (2, 9, 85): "Honestly, that sounds fair.",
    (2, 9, 86): (
        "Curse you! I'll squeeze out my last strength and coat your entire bodies in slime!"
    ),
    (2, 9, 87): "Gross! Stop! The fight is already over!",
    (2, 9, 88): (
        "Silence! Lord Barbamon must have foreseen this too. At least I'll leave Spadamon unable to fight!"
    ),
    (2, 9, 89): "No thanks! If that thing wraps around me, my nose is done for!",
    (2, 9, 90): "Ugh... If only there were some way to drive him off...",
    (2, 9, 91): (
        "That's it! Hit the squid with a phrase that cuts deep! Maybe it'll scare him away!"
    ),
    (2, 9, 92): "A phrase that scares off squid? W-what does that even mean?!",
    (2, 9, 93): "Raaaaah! Take this!",
    (2, 9, 94): "Now, Spadamon!",
    (2, 9, 95): "Y-your... Your mom is seafood!",
    (2, 9, 96): "Gwaaaah!",
    (2, 9, 97): "We did it!",
    (2, 9, 98): "All right!",
    (2, 9, 99): "...Wait. That actually worked?",
    (2, 9, 100): "We beat him, so let's not question it!",
    (2, 9, 101): "Switched to Normal Mode!",
    (2, 9, 102): (
        "I never told anyone about that weakness. Barbamon really is terrifying."
    ),
    (2, 9, 103): (
        "Nah, he probably guessed from your appearance. They say feeding squid to a cat makes its legs go weak."
    ),
    (2, 9, 104): "Well, Spadamon does look like a cat. It makes sense.",
    (2, 9, 105): "I'm not a cat!",
    (2, 9, 106): "Let's hurry to the next Tower!",
    (2, 9, 107): "Checkmate!",
    (2, 9, 108): "Watch out! It's a Shadow Guard!",
    (2, 9, 109): (
        "I'm RookChessmon, the Lazy Elite of Barbamon's Shadow Guard, sent to protect this Capacitor Tower. Yeah?"
    ),
    (2, 9, 110): "Damn it, this guy's a joke too!",
    (2, 9, 111): "Is he plotting something...?",
    (2, 9, 112): (
        "What a lousy audience. Fine, I'll spell it out. You're already checkmated--cornered with nowhere to move. "
        "You know you'll lose, so why bother fighting? Yeah?"
    ),
    (2, 9, 113): "We're checkmated? And... constipated? What does he mean?",
    (2, 9, 114): (
        "You really don't get it? I absolutely won't lose, so you can't possibly win. Yeah?"
    ),
    (2, 9, 115): "Uh... what?",
    (2, 9, 116): "Don't let your guard down, Spadamon. Here he comes!",
    (2, 9, 117): "How's that? Checkmate!",
    (2, 9, 118): (
        "Sorry, but no. You can't take the king. No matter how badly I lose, I'm only a rook. Yeah?"
    ),
    (2, 9, 119): (
        "I'm going to be the Digimon King! I'm not losing to some lowly rook!"
    ),
    (2, 9, 120): (
        "That's quite a dream. But the true king will be Lord Barbamon, wielding the legendary Weapon Digimon. Yeah?"
    ),
    (2, 9, 121): "We won't let that happen!",
    (2, 9, 122): (
        "Only an idiot walks off a cliff because he can't see the road ahead. Apologize to Lord Barbamon while you can. Yeah?"
    ),
    (2, 9, 123): "No matter how often you say 'yeah,' we won't change our minds!",
    (2, 9, 124): (
        "A real checkmate will be far worse than this. Anyway, I'm off to be absorbed by Lord Barbamon. Yeah?"
    ),
    (2, 9, 125): "H-hey, wait...",
    (2, 9, 126): "Barbamon is treating all of us like game pieces!",
    (2, 9, 127): (
        "He doesn't understand anything. I'm the future Digimon King! Yeah?"
    ),
    (2, 9, 128): "You picked up his catchphrase!",
    (2, 9, 129): "Anyway, I'll restore the Tower.",
    (2, 9, 130): "Switched to Normal Mode!",
    (2, 9, 131): "Good! This Tower is back in the right mode.",
    (2, 9, 132): "Hmm...?",
    (2, 9, 133): "Something wrong?",
    (2, 9, 134): (
        "Are these really all the Capacitor Towers? I feel like there was another one somewhere."
    ),
    (2, 9, 135): (
        "You said the same thing after we beat Pharaohmon in Papyrus Desert. You thought there were seven Towers, not six."
    ),
    (2, 9, 136): "Didn't you just count wrong?",
    (2, 9, 137): "...Maybe?",
    (2, 9, 138): (
        "I told you to count with DigiNoir! First there's Skyfort, then Knuckle Coast... Man, I'm getting hungry..."
    ),
    (2, 9, 139): "Ahaha... Let's keep moving for now.",
    (2, 9, 140): (
        "When we get back to Skyfort, let's ask Patamon and the others. Maybe they know something."
    ),
    (2, 9, 141): "One little piece of garbage!",
})

# Batch 2T: global prose records 1942-2024 (1,003 draft-English words).
# Garbagemon trio, the seventh system, and Dynasmon's final test.
OVERRIDES.update({
    (2, 9, 142): "Two little pieces of garbage!",
    (2, 9, 143): "Three little pieces of garbage!",
    (2, 9, 144): (
        "Three together make a mountain of garbage! We are the Heavy-Smell Elites of Barbamon's Shadow Guard, "
        "sent to protect this Capacitor Tower! We are the Garbagemons!"
    ),
    (2, 9, 145): (
        "Shadow Guards! Are all three the leaders, or is only one of them real?"
    ),
    (2, 9, 146): "Forget that for a second--they smell awful!",
    (2, 9, 147): "Grimy garbage is filthy garbage!",
    (2, 9, 148): "Dirty garbage is odious garbage!",
    (2, 9, 149): "Messy garbage is smelly garbage!",
    (2, 9, 150): "Frumpy, stinky chunks of garbage!",
    (2, 9, 151): "I can't understand a word they're saying!",
    (2, 9, 152): "D-don't move! The smell is drifting this way...",
    (2, 9, 153): "You'll understand what we mean soon enough, bage!",
    (2, 9, 154): "We'll pound the lesson into you until it hurts, bage!",
    (2, 9, 155): "The smell will stain itself deep in your memories, bage!",
    (2, 9, 156): "Wh-what does that even mean...?",
    (2, 9, 157): (
        "I don't understand them at all, but their strength and their stench are coming through loud and clear!"
    ),
    (2, 9, 158): "Garbage!",
    (2, 9, 159): "How's thad?! We bead 'em!",
    (2, 9, 160): "...Taiki, why are you talking like that?",
    (2, 9, 161): "He's trying not to breathe through his nose because of the smell.",
    (2, 9, 162): "Those who laugh at garbage will cry before Lord Barbamon, bage!",
    (2, 9, 163): "Pile up enough garbage, and it becomes Lord Barbamon, bage!",
    (2, 9, 164): "Everything in this world goes around--Lord Barbamon is garbage!",
    (2, 9, 165): "We won't let Barbamon do whatever he wants!",
    (2, 9, 166): "Garbagemon, we will not lose to Barbamon!",
    (2, 9, 167): "Garbage!",
    (2, 9, 168): "Ugh... That area looks like it reeks.",
    (2, 9, 169): "Switched to Normal Mode!",
    (2, 9, 170): "This Tower is back in Normal Mode too.",
    (2, 9, 171): (
        "Once we reclaim every Capacitor Tower, the Protection Field will disappear, right?"
    ),
    (2, 9, 172): "...I don't think it will.",
    (2, 9, 173): "Wait, Spadamon! Where did that come from?!",
    (2, 9, 174): (
        "Returning the Towers is the right approach. But I feel like I've forgotten something important..."
    ),
    (2, 9, 175): "Something important...?",
    (2, 9, 176): (
        "There are six Capacitor Towers... but how many Capacitor Systems? "
        "No, I can't think clearly. What's happening to me?"
    ),
    (2, 9, 177): "Spadamon, I'm sure we'll understand if we keep moving.",
    (2, 9, 178): "Thank you for reclaiming the Towers! You guys are incredible!",
    (2, 9, 179): "Then Skyfort's Protection-whatever is gone now, right?!",
    (2, 9, 180): (
        "No, it hasn't stopped! There's one more Capacitor System we need to shut down!"
    ),
    (2, 9, 181): "What?!",
    (2, 9, 182): (
        "I was shocked too. The moment Spadamon returned the sixth Tower to Normal Mode, "
        "Earthfort suddenly received a transmission from another system."
    ),
    (2, 9, 183): "What did it say?!",
    (2, 9, 184): "Only that we should come to Stealth Valley.",
    (2, 9, 185): (
        "There were six Towers but seven systems. Spadamon's memory was right after all."
    ),
    (2, 9, 186): (
        "But who manages that system? If someone sent the message, somebody must be there..."
    ),
    (2, 9, 187): (
        "It's strange. How did they hide the system from ROG this whole time? It isn't even on the map. "
        "Only an incredibly intelligent Digimon could rewrite the Zone data."
    ),
    (2, 9, 188): "It could be another of Barbamon's traps.",
    (2, 9, 189): (
        "Maybe, but the voice from the system was calm and powerful. I felt nervous even though it wasn't angry."
    ),
    (2, 9, 190): "Oh, and it specifically asked Taiki's team to come too.",
    (2, 9, 191): "It knows about us...",
    (2, 9, 192): (
        "I located Stealth Valley's port, so you can fly there whenever you're ready!"
    ),
    (2, 9, 193): (
        "Spadamon, wasn't Dynasmon the administrator of the Capacitor Systems?"
    ),
    (2, 9, 194): (
        "Dynasmon, the warrior who protected the Zone beside the Weapon Digimon... Is he calling us? "
        "But why is he hiding in Stealth Valley when he's supposed to protect the Zone?"
    ),
    (2, 9, 195): "There must be a reason. Let's hurry to Stealth Valley!",
    (2, 9, 196): "Were you the one who summoned us...?",
    (2, 9, 197): (
        "Indeed, Kudou Taiki. I am Dynasmon--the one who was supposed to protect this Zone."
    ),
    (2, 9, 198): "Was supposed to...?",
    (2, 9, 199): (
        "I was a warrior who led the Weapon Digimon in battle. I was meant to defend this Zone from invasion. "
        "But all I managed to protect was this small memory."
    ),
    (2, 10, 0): (
        "Come, Spadamon. I will return your final memory, which you once entrusted to me."
    ),
    (2, 10, 1): "Wait, Spadamon! Are you sure we can trust him?",
    (2, 10, 2): "All of Spadamon's abilities have been restored!",
    (2, 10, 3): "Spadamon, are you okay?",
    (2, 10, 4): "Dynasmon! I finally remember everything!",
    (2, 10, 5): (
        "It has been a long time, Spadamon. Now show me the strength of the allies you chose."
    ),
    (2, 10, 6): (
        "Y-yes! With Xros Heart beside me, I know we can protect the El Estou Zone!"
    ),
    (2, 10, 7): "H-hey! Spadamon, what's going on?!",
    (2, 10, 8): "I-I'll do my best on the final test!",
    (2, 10, 9): "A test? What kind of test?!",
    (2, 10, 10): "Team Xros Heart! I will not hold back. Face me with all your strength!",
    (2, 10, 11): (
        "Damn it! I don't know what's going on, but we'll give it everything we've got!"
    ),
    (2, 10, 12): (
        "Spadamon, you pass. You have grown strong... truly strong."
    ),
    (2, 10, 13): "Why did you suddenly attack us?!",
    (2, 10, 14): "Explain yourself! What exactly did we pass?!",
    (2, 10, 15): "...How much do you know about the Weapon Digimon?",
    (2, 10, 16): (
        "It has enough power to destroy the world, and for some reason it's sealed in Lost Space. "
        "Barbamon called it Armamon. That's all we know."
    ),
    (2, 10, 17): (
        "That isn't wrong, but you misunderstand one thing. Armamon isn't this Zone's only Weapon Digimon. "
        "Spadamon is one of the surviving Weapon Digimon too."
    ),
    (2, 10, 18): "Spadamon is a Weapon Digimon?!",
    (2, 10, 19): (
        "Long ago, many Weapon Digimon lived in this Zone. Each chose a warrior as its partner, "
        "and together they defended the Zone. Spadamon was the youngest among them. "
        "I sealed his memories to protect him from the invaders."
    ),
    (2, 10, 20): "I see... So that's why Spadamon could activate the Towers...",
    (2, 10, 21): "Dynasmon must have...",
    (2, 10, 22): (
        "No, I don't think so. Only an administrator can open a Tower, right? "
        "Dynasmon probably locked the doors so only Spadamon could open them."
    ),
    (2, 10, 23): (
        "As expected of the boy Spadamon chose. The only way to protect the young Spadamon was for him to grow stronger. "
        "So I made each door open as he developed. Everything was meant to train him."
    ),
    (2, 10, 24): (
        "Hey, Dynasmon! Weren't you the warrior meant to protect this Zone? "
        "You had an incredibly powerful Weapon Digimon partner too! Why didn't you fight?!"
    ),
})

# Batch 2U: global prose records 2025-2105 (1,004 draft-English words).
# Armamon's fall, Dynasmon's sacrifice, and the return to Skyfort.
OVERRIDES.update({
    (2, 10, 25): "Calm down, Shoutmon! There must have been a reason.",
    (2, 10, 26): (
        "Right, Dynasmon? I can feel how deeply you care about protecting Spadamon. "
        "Someone like you wouldn't hide here alone without a reason!"
    ),
    (2, 10, 27): "T-Taiki is right. Dynasmon...",
    (2, 10, 28): (
        "During the long war to protect this Zone, my partner was the strongest Weapon Digimon. "
        "But it became intoxicated by its own power and forgot its duty to defend the Zone. That Digimon was Armamon."
    ),
    (2, 10, 29): (
        "I sealed the rampaging Armamon, but my DigiCore suffered terrible damage. "
        "I now preserve my data only by drawing energy from this Capacitor System. "
        "If I leave this place, my data will disappear."
    ),
    (2, 10, 30): "I see... I'm sorry, Dynasmon.",
    (2, 10, 31): (
        "It's all right, Shoutmon. Because you trained Spadamon, hope has returned to the El Estou Zone. "
        "Please stop Barbamon before he revives Armamon. I'm counting on you."
    ),
    (2, 10, 32): (
        "I'm asking too. I want to save this Zone and everyone in it! Please fight beside me!"
    ),
    (2, 10, 33): "Of course! You don't even have to ask, Spadamon!",
    (2, 10, 34): (
        "What are you talking about, Spadamon? You've been one of us for ages!"
    ),
    (2, 10, 35): "Th-thank you, both of you!",
    (2, 10, 36): (
        "I can't abandon the El Estou Zone! We will stop Barbamon!"
    ),
    (2, 10, 37): "Leave it to us! We'll bring peace back to this Zone!",
    (2, 10, 38): (
        "Thank you, everyone. I am grateful from the bottom of my heart. "
        "Spadamon, restore this Capacitor System and release Skyfort's Protection Field."
    ),
    (2, 10, 39): "...Yes.",
    (2, 10, 40): "The Protection Field has been disabled!",
    (2, 10, 41): "Now we can go save everyone at Skyfort!",
    (2, 10, 42): "We did it, Taiki! Let's head back right away!",
    (2, 10, 43): (
        "One more thing. A Digimon was searching for you, so I summoned him to the El Estou Zone."
    ),
    (2, 10, 44): "Could it be...?",
    (2, 10, 45): "...Beelzebumon!",
    (2, 10, 46): "Taiki! Shoutmon! You're safe!",
    (2, 10, 47): "...Who is he? A friend of Taiki's?",
    (2, 10, 48): (
        "This Digimon is your ally, correct? He was searching for you in another Zone, "
        "so I forcibly pulled him into this one."
    ),
    (2, 10, 49): "...Hey, Taiki? Something just occurred to me. What if we were also...",
    (2, 10, 50): (
        "Yeah, probably. Dynasmon must have brought us here to help Spadamon. "
        "...But I guess it worked out in the end."
    ),
    (2, 10, 51): "R-right! It's how we met Spadamon!",
    (2, 10, 52): (
        "Beelzebumon! We're fighting villains in this Zone. Please help us save its Digimon!"
    ),
    (2, 10, 53): (
        "Hmph. Still helping others wherever you go, I see. If Taiki asks, I'll gladly lend my strength."
    ),
    (2, 10, 54): "Thanks, Beelzebumon!",
    (2, 10, 55): "Thank you, Beelzebumon... and thank you, Taiki and Shoutmon.",
    (2, 10, 56): (
        "It's okay, Dynasmon. I just can't ignore people who need our help."
    ),
    (2, 10, 57): "That's Taiki for you! He's our General!",
    (2, 10, 58): (
        "Until ROG is defeated and this Zone is reclaimed, nobody can travel to another Zone. "
        "That means you cannot return either."
    ),
    (2, 10, 59): (
        "What's that supposed to mean? You dragged me here without asking, and now I can't leave? "
        "Where am I supposed to go or what am I supposed to do?"
    ),
    (2, 10, 60): (
        "Beelzebumon, wait at Earthfort east of Crystal Volcano for now. We'll join you soon."
    ),
    (2, 10, 61): "...Understood. I'll wait there.",
    (2, 10, 62): (
        "Beelzebumon, it would really help if you fought alongside us."
    ),
    (2, 10, 63): (
        "I have nothing else to do, so I'll lend a hand. Call me when you need me. Later."
    ),
    (2, 10, 64): (
        "It seems I have little time left, but I can summon any other allies you need."
    ),
    (2, 10, 65): "Don't make it sound like we're ordering allies from a catalog...",
    (2, 10, 66): (
        "Then what about Nene? Can you find her? Barbamon sent her somewhere..."
    ),
    (2, 10, 67): "...I see. Give me a moment.",
    (2, 10, 68): "She isn't anywhere within the reach of my power.",
    (2, 10, 69): (
        "What does that mean?! Is she merely missing, or could she already be...?"
    ),
    (2, 10, 70): (
        "No. The transit data shows no missing pieces, damage, or injuries. She is probably safe. "
        "I cannot determine where she was sent without further investigation."
    ),
    (2, 10, 71): (
        "That's enough, Dynasmon. Thank you. For now, knowing she's safe is all I need."
    ),
    (2, 10, 72): "...I see.",
    (2, 10, 73): "Dynasmon?!",
    (2, 10, 74): "W-what's wrong?",
    (2, 10, 75): "...At last... it seems my time has come...",
    (2, 10, 76): "Your time? What do you mean?",
    (2, 10, 77): "D-Dynasmon! Your data is...",
    (2, 10, 78): "You mean you're disappearing?!",
    (2, 10, 79): "Why now, when we still need you?!",
    (2, 10, 80): (
        "Dynasmon preserved his data using this system's energy. Once the system resumed operation, "
        "there was nothing left to sustain him..."
    ),
    (2, 10, 81): "You knew this would happen...",
    (2, 10, 82): "Spa... damon... Xros... Heart... I'm counting... on you...",
    (2, 10, 83): "Thank you, Dynasmon...",
    (2, 10, 84): (
        "Taiki, let's return to Earthfort. Something must have changed by now."
    ),
    (2, 10, 85): "Yeah...",
    (2, 10, 86): "You're finally back! Listen, everyone--this is serious!",
    (2, 10, 87): (
        "What's wrong? If you're worried about the Protection-whatever, it'll disappear properly. Relax!"
    ),
    (2, 10, 88): "I know. I trust you completely!",
    (2, 10, 89): "Then why are you panicking?",
    (2, 10, 90): (
        "Because Lost Space suddenly appeared near Skyfort!"
    ),
    (2, 10, 91): "What?!",
    (2, 10, 92): (
        "The Digimon flight squad can depart immediately. Once you're ready, hurry to Skyfort!"
    ),
    (2, 10, 93): "W-what do we do, Taiki?!",
    (2, 10, 94): "I'm worried about Akari, Zenjirou, and everyone else!",
    (2, 10, 95): "Let's get back to Skyfort, fast!",
    (2, 10, 96): "Thanks for everything, Hououmon.",
    (2, 10, 97): (
        "I'll wait here. Tell me whenever you need to travel somewhere!"
    ),
    (2, 10, 98): "Taiki! Welcome back!",
    (2, 10, 99): "Thank goodness you're back! What a relief!",
    (2, 10, 100): (
        "Akari, Zenjirou, Patamon--you're safe! What about everyone else? Is anybody missing?"
    ),
    (2, 10, 101): "Everyone's okay. We somehow kept everybody safe!",
    (2, 10, 102): (
        "Things got really bad after you left for Crystal Volcano."
    ),
    (2, 10, 103): (
        "The volcano near Earthfort erupted, and a huge shadow rushed toward us at incredible speed. "
        "Just as it was about to land, a crackling barrier suddenly appeared around Skyfort."
    ),
    (2, 10, 104): (
        "The barrier kept the shadow out, but it also trapped all of us inside."
    ),
    (2, 10, 105): (
        "Then the barrier suddenly vanished a moment ago, and the shadow came back!"
    ),
})

# Batch 2V: global prose records 2106-2282 (2,002 draft-English words).
# The Omega Area, Armamon's revival, and the final battle.
OVERRIDES.update({
    (2, 10, 106): "That shadow has to be Barbamon!",
    (2, 10, 107): "Barbamon? Is that a Digimon?",
    (2, 10, 108): (
        "A terrifying one! Barbamon was controlling ROG--and everything else--from the shadows!"
    ),
    (2, 10, 109): "But the shadow didn't seem interested in us at all.",
    (2, 10, 110): "Really?",
    (2, 10, 111): "Yeah. It flew right past us at incredible speed.",
    (2, 10, 112): "That's right! It headed toward Sky Garden!",
    (2, 10, 113): "Sky Garden? There wasn't anything there, was there?",
    (2, 10, 114): "Only an old windmill, as far as I know.",
    (2, 10, 115): "We'll never know unless we check. Let's go, Taiki!",
    (2, 10, 116): "Right!",
    (2, 10, 117): "Then what should we do?",
    (2, 10, 118): (
        "The Digimon who hid from ROG may start coming back. Let's wait for them at Skyfort!"
    ),
    (2, 10, 119): "Agreed!",
    (2, 10, 120): "All right! I'll help support everyone too!",
    (2, 10, 121): (
        "Akari and the others are bursting with energy! Guess we didn't need to worry!"
    ),
    (2, 10, 122): (
        "I'm just glad everyone is safe. All that's left is stopping Armamon's revival!"
    ),
    (2, 10, 123): "You're Xros Heart, aren't you? You shall go no farther!",
    (2, 10, 124): (
        "We are Deathmon and Boltmon, Bloody Elites of Barbamon's Shadow Guard, "
        "sent to protect the secret entrance! Bollll!"
    ),
    (2, 10, 125): "What is this?! Does the path ahead lead to Lost Space?!",
    (2, 10, 126): "How do you know that?!",
    (2, 10, 127): "I knew it! Taiki, Lost Space is just ahead!",
    (2, 10, 128): "We have to defeat Barbamon. Get out of our way!",
    (2, 10, 129): "Boooooollll! You shall not pass!",
    (2, 10, 130): (
        "Your resistance is useless! Lord Barbamon has already located the Omega Area inside Lost Space!"
    ),
    (2, 10, 131): (
        "We Shadow Guards will gather there, be absorbed by Armamon, and become the ultimate weapon! "
        "We look forward to destroying you! Bol-bol-bollll!"
    ),
    (2, 10, 132): "We're out of time! We have to enter Lost Space now!",
    (2, 10, 133): "Wait!",
    (2, 10, 134): (
        "This warp gate isn't on the map. The El Estou Zone's data must be distorted. "
        "We don't know whether this is Barbamon's power, so we need to be fully prepared before entering Lost Space."
    ),
    (2, 10, 135): "What's wrong, Spadamon? Getting scared?",
    (2, 10, 136): "N-no! I just want us to prepare properly!",
    (2, 10, 137): "Spadamon is right. Let's make sure we're ready!",
    (2, 10, 138): "Stop. You will go no farther.",
    (2, 10, 139): (
        "We are SlashAngemon and LordKnightmon, Last-Heaven Elites of Barbamon's Shadow Guard, "
        "sent to defend the gate to the Omega Area."
    ),
    (2, 10, 140): "Move! We have to stop Barbamon!",
    (2, 10, 141): (
        "We cannot allow that. Lord Barbamon is busy preparing Armamon's revival."
    ),
    (2, 10, 142): "If they're here, the Omega Area is close. Let's blow them away!",
    (2, 10, 143): "Barbamon is just ahead. We're counting on you, Taiki!",
    (2, 10, 144): "You will never reach the Omega Area. You disappear here.",
    (2, 10, 145): "L-Lord... Barbamon... forgive us...",
    (2, 10, 146): (
        "Everything... for Lord Barbamon... to claim the world... Turn us... into his weapon..."
    ),
    (2, 10, 147): "This warp gate leads to the Omega Area, right?",
    (2, 10, 148): "Yeah... I think so.",
    (2, 10, 149): (
        "The Shadow Guard said Barbamon was preparing to revive Armamon."
    ),
    (2, 10, 150): (
        "If Armamon becomes his weapon, something terrible will happen!"
    ),
    (2, 10, 151): (
        "Armamon was a Weapon Digimon like me, but we cannot let Barbamon break its seal--for Dynasmon's sake too."
    ),
    (2, 10, 152): "Right. We'll stop Barbamon and protect this Zone. To the Omega Area!",
    (2, 10, 153): (
        "Compound System: DigiCore load initiated. Data fixed at 72 percent. 28 percent remains."
    ),
    (2, 10, 154): "Add Minotaurmon, Pukumon, and Minervamon.",
    (2, 10, 155): "Data injection complete. Load increased to 84 percent.",
    (2, 10, 156): (
        "Good. Add IceDevimon, Arukenimon, and Pharaohmon. Load ZDMillenniummon last."
    ),
    (2, 10, 157): "There he is--Barbamon!",
    (2, 10, 158): "What is he doing?!",
    (2, 10, 159): "No! System Omega is running!",
    (2, 10, 160): "What?!",
    (2, 10, 161): "Stop, Barbamon!",
    (2, 10, 162): "Well, well... Xros Heart and Spadamon survived.",
    (2, 10, 163): "Don't touch System Omega! Step away from it!",
    (2, 10, 164): (
        "Your memories have returned, Spadamon. Then you know what this is. "
        "Yes--the dream machine that will resurrect Armamon: System Omega!"
    ),
    (2, 10, 165): (
        "Stop, Barbamon! Armamon's power could destroy not only this Zone, but the entire Digital World!"
    ),
    (2, 10, 166): (
        "Hahaha! That is precisely why it is worthy of becoming my weapon. "
        "With Armamon, the Digital World will be mine. As a fellow Weapon Digimon, "
        "you should remember the joy of serving the strong."
    ),
    (2, 10, 167): (
        "Strength means nothing when its owner is evil! Weapon Digimon don't exist to destroy. "
        "We fight to protect what matters. Once a Weapon Digimon forgets that duty and runs wild, nobody can stop it!"
    ),
    (2, 10, 168): (
        "How foolish the weak can be. Dynasmon restored useless memories to you, "
        "but Armamon destroyed him. He was worthless scrap data."
    ),
    (2, 10, 169): "Don't insult Dynasmon!",
    (2, 10, 170): (
        "Why object to calling unusable material scrap? Had his DigiCore been intact, "
        "his data might have been as useful as ROG's leaders."
    ),
    (2, 10, 171): "ROG's leader Digimon? What did you do with their data?!",
    (2, 10, 172): (
        "System Omega requires DigiCores with dark hearts to revive Armamon. "
        "I controlled ZDMillenniummon with illusions and made him gather ROG's leaders. "
        "Incidentally, the object to your left is ZDMillenniummon's DigiCore."
    ),
    (2, 10, 173): "You sacrificed other Digimon's lives for your own ambition?!",
    (2, 10, 174): (
        "In the Digital World, the weak are consumed by the strong. Why can't you accept the natural order? "
        "Surely your group has useless members too. I offer them the joy of being reborn as something powerful."
    ),
    (2, 10, 175): (
        "Quit talking nonsense! None of our friends are useless! You fed your own allies to Armamon, "
        "and now you're all alone. You can't beat us!"
    ),
    (2, 10, 176): (
        "Three weaklings remain weak. But what if there were three of me?"
    ),
    (2, 10, 177): "What?! Barbamon multiplied!",
    (2, 10, 178): (
        "I alone need exist. Barbamon will fill the world--identical in power, personality, height, weight, "
        "and even the shape of our toes. Above them all will stand me, master of Armamon."
    ),
    (2, 10, 179): (
        "In one sense, each of us is the original. In another, every one of us is a copy."
    ),
    (2, 10, 180): "Now taste attacks identical down to the smallest detail!",
    (2, 10, 181): "We did it! We beat him in time!",
    (2, 10, 182): "No. You're already too late.",
    (2, 10, 183): "Armamon awakens now!",
    (2, 10, 184): "Arise, Armamon! Become my blade!",
    (2, 10, 185): (
        "Final data injection. 98 percent... 99 percent... 100 percent. "
        "Compound limit reached. Restoring Armamon."
    ),
    (2, 10, 186): "That's Armamon?!",
    (2, 10, 187): "It feels completely different from Spadamon...",
    (2, 10, 188): "F-fwahahaha! Magnificent! I never imagined such power!",
    (2, 10, 189): "My name is Armamon. Are you the one who awakened me?",
    (2, 10, 190): (
        "Yes, it was I! I claimed you so I could possess the entire Digital World!"
    ),
    (2, 10, 191): (
        "Armamon, let me test your blade! First, cut down every Digimon in the El Estou Zone!"
    ),
    (2, 10, 192): "What did he say?!",
    (2, 10, 193): (
        "Now that the ultimate Weapon Digimon is revived, the El Estou Zone has no further value. "
        "Let me enjoy its destruction as a final diversion!"
    ),
    (2, 10, 194): "Hurry, Armamon! Transform into a weapon--",
    (2, 10, 195): (
        "If my owner desires it, ruling the Digital World is entirely possible. That much is correct. "
        "The problem is your vulgar behavior."
    ),
    (2, 10, 196): "Wh-what?! Armamon, what are you saying?",
    (2, 10, 197): (
        "You covet me. You covet the Digital World. Want, want, want--you want everything. "
        "Such greed does not suit my tastes."
    ),
    (2, 10, 198): "...Wait, Armamon. What are you doing...?",
    (2, 10, 199): (
        "You have failed, Barbamon. Regrettably, we must part. You are not worthy to be my master."
    ),
    (2, 11, 0): "Wh-wh-wh-wh-what?!",
    (2, 11, 1): "What just happened?!",
    (2, 11, 2): "...Hmm. Not a bad weapon.",
    (2, 11, 3): "Spadamon! Is that what becoming a weapon means?!",
    (2, 11, 4): (
        "N-no! Weapon Digimon transform their own bodies into weapons. "
        "They never force other Digimon to become weapons!"
    ),
    (2, 11, 5): (
        "Calm down, both of you. Armamon may still remember protecting this Zone. Let's try talking to him."
    ),
    (2, 11, 6): "Armamon! Listen to us!",
    (2, 11, 7): "My name is Armamon. Who are you?",
    (2, 11, 8): (
        "We don't want your power to conquer the world. Do you remember protecting this Zone with Dynasmon?"
    ),
    (2, 11, 9): "...You are Dynasmon's allies?",
    (2, 11, 10): (
        "A trace of his data drifts around you. You must have encountered him."
    ),
    (2, 11, 11): (
        "That's right! We're friends of Dynasmon, your former partner. We aren't your enemies!"
    ),
    (2, 11, 12): "I understand. You are Dynasmon's allies--therefore, you are my enemies!",
    (2, 11, 13): "How did you reach that conclusion?!",
    (2, 11, 14): (
        "Armamon forgot the duty of a Weapon Digimon. He's unchanged from when Dynasmon sealed him!"
    ),
    (2, 11, 15): (
        "Curse Dynasmon! He discovered my plan and imprisoned me like this!"
    ),
    (2, 11, 16): "Your plan...?",
    (2, 11, 17): (
        "Gather every Digimon in this Zone into System Omega and forge them into a single weapon. That is my plan!"
    ),
    (2, 11, 18): (
        "What?! You can't turn ordinary Digimon into weapons! That's absolutely wrong!"
    ),
    (2, 11, 19): "Nyaaah...",
    (2, 11, 20): "S-Spadamon?! Are you okay?!",
    (2, 11, 21): (
        "B-be careful... That attack turned Barbamon into a weapon. I'm a Weapon Digimon, so I-I'm okay."
    ),
    (2, 11, 22): "Are you serious?!",
    (2, 11, 23): "Stop this, Armamon!",
    (2, 11, 24): (
        "Why can't Dynasmon or any of you understand my magnificent plan? "
        "System Omega is the only way to protect this Zone from every invader. I will show no mercy to those who interfere!"
    ),
    (2, 11, 25): "...Where is he?",
    (2, 11, 26): "Huh?",
    (2, 11, 27): "Where is he...?",
    (2, 11, 28): "Where is who...?",
    (2, 11, 29): "Wh-why... all of a sudden...?",
    (2, 11, 30): "...Where is Dynasmon?",
    (2, 11, 31): "Are you okay?!",
    (2, 11, 32): "If I weren't a Weapon Digimon, that attack would've turned me into one...",
    (2, 11, 33): (
        "System Omega: accessing mainframe. Searching for Dynasmon. Beginning full scan."
    ),
    (2, 11, 34): (
        "Checkpoint 82039. Search complete. Dynasmon: Digimon ID lost. "
        "Final confirmed location: Stealth Valley."
    ),
    (2, 11, 35): "Armamon... Dynasmon is gone.",
    (2, 11, 36): "B-but... why...?",
    (2, 11, 37): "...Silence!",
    (2, 11, 38): "What's Armamon doing?",
    (2, 11, 39): "His ID is lost?! Dynasmon... No, it can't be...",
    (2, 11, 40): "What is Armamon trying to do?",
    (2, 11, 41): (
        "He's returning to the machine. Maybe he intends to seal himself again."
    ),
    (2, 11, 42): "...No. Something feels terribly wrong.",
    (2, 11, 43): "Look!",
    (2, 11, 44): "Whaaaat?! He can't possibly be--",
    (2, 11, 45): "Spadamon, what is it?!",
    (2, 11, 46): (
        "Armamon is using System Omega to absorb data! He sensed traces of Dynasmon's data around us. "
        "He must be searching for those traces!"
    ),
    (2, 11, 47): (
        "He's absorbing all the data nearby with System Omega, then trying to reconstruct Dynasmon from it?"
    ),
    (2, 11, 48): "Is that even possible?!",
    (2, 11, 49): (
        "No! Even if he reconstructs something, it won't truly be Dynasmon!"
    ),
    (2, 11, 50): "Why...? He has to understand that...",
    (2, 11, 51): (
        "Compound System: free load initiated. Data owner functionality will be temporarily restricted. "
        "Compound System: free load initiated. Data owner functionality will be temporarily restricted."
    ),
    (2, 11, 52): "Taiki! Are you okay?!",
    (2, 11, 53): "S-somehow... What happened?",
    (2, 11, 54): "Taiki, this is bad! Look, quickly!",
    (2, 11, 55): "Dynasmon... Where are you?",
    (2, 11, 56): "...Is that still Armamon?",
    (2, 11, 57): "I've never seen a Digimon that dangerous...",
    (2, 11, 58): (
        "No... That's OmegaArmamon Burst Mode, the legendary Weapon Digimon of the El Estou Zone!"
    ),
    (2, 11, 59): "How can we possibly stop something like that...?",
    (2, 11, 60): (
        "Collected Digimon data: 90384795038910. Acquired Digimon data: 54395084537. "
        "Dynasmon ID unconfirmed. No trace of Dynasmon."
    ),
    (2, 11, 61): (
        "Dynasmon... Why won't you understand me? There still isn't enough data. If I go to Stealth Valley..."
    ),
    (2, 11, 62): "Spadamon, we can't let him leave this place!",
    (2, 11, 63): (
        "As a Weapon Digimon, I may be able to access System Omega. Wait--I'll try!"
    ),
    (2, 11, 64): (
        "Security protocol activated. Gate code rejected. Initiating full protection of the Omega Area."
    ),
    (2, 11, 65): "What...?",
    (2, 11, 66): "Omega Area full protection complete. Omega Area full protection complete.",
    (2, 11, 67): "Why...? Why are you stopping me?!",
    (2, 11, 68): "Rrraaaaaaaaaah...!",
    (2, 11, 69): "I managed to seal off the Omega Area!",
    (2, 11, 70): "What happens to Armamon now?!",
    (2, 11, 71): (
        "Armamon is completely linked to System Omega. If we leave him, he'll consume Lost Space "
        "and then the entire El Estou Zone. Taiki, Shoutmon--this is the final battle. Please lend me your strength!"
    ),
    (2, 11, 72): (
        "Of course! We'll defeat him, then all three of us will return to Skyfort together. Let's go!"
    ),
    (2, 11, 73): "Yeah!",
    (2, 11, 74): "Leave it to us!",
    (2, 11, 75): "Rrraaaaaaaaaah!",
    (2, 11, 76): "D-Dynasmon... Where... are you?",
    (2, 11, 77): (
        "Abnormality detected in Armamon's DigiCore. Forcibly terminating data download."
    ),
    (2, 11, 78): (
        "Forced termination failed. Armamon DigiCore abnormality confirmed. DigiCore damage: 10 percent."
    ),
    (2, 11, 79): (
        "Armamon's DigiCore is breaking down! He can't contain all the incoming data. "
        "There's almost no time before it overflows!"
    ),
    (2, 11, 80): (
        "Do we have to erase him completely? But how can we stop something that huge?!"
    ),
    (2, 11, 81): (
        "Armamon DigiCore damage: 20 percent... 30 percent... 40 percent..."
    ),
    (2, 11, 82): "Don't... leave me... alone...",
})

# Batch 2W: global prose records 2283-2437 (2,003 draft-English words).
# Spadamon's sacrifice and return, the Code Crown, and alternate Kiriha route.
OVERRIDES.update({
    (2, 11, 83): "There has to be something we can do!",
    (2, 11, 84): "Armamon DigiCore damage: 50 percent... 70 percent... 80 percent...",
    (2, 11, 85): "No! The overflow is starting!",
    (2, 11, 86): "Dynasmoooooon!",
    (2, 11, 87): (
        "Armamon DigiCore damage: 90 percent... 100 percent. Code red. Code red. "
        "Evacuate Lost Space immediately."
    ),
    (2, 11, 88): "It's a black hole! If it pulls us in, we'll never come back!",
    (2, 11, 89): "We have to escape!",
    (2, 11, 90): "The warp gate is broken?!",
    (2, 11, 91): (
        "The Gate Disk won't work because I sealed the Omega Area... But maybe I can..."
    ),
    (2, 11, 92): "Are you two ready?",
    (2, 11, 93): "You found a way out?",
    (2, 11, 94): (
        "Of course! I can use System Omega's remaining functions to transfer both of you to Skyfort."
    ),
    (2, 11, 95): "Then say so sooner! You had me worried!",
    (2, 11, 96): (
        "Ahaha, sorry! Finding the right system was hard. Don't worry--you'll both return safely."
    ),
    (2, 11, 97): "Spadamon... You aren't planning to stay here alone, are you?!",
    (2, 11, 98): (
        "Why the long face, Taiki? I'll be okay. I'm the one who can stop Armamon."
    ),
    (2, 11, 99): "No! We can't leave you behind!",
    (2, 11, 100): (
        "I understand what Armamon wanted because I'm a Weapon Digimon too. "
        "I can't abandon him. Are you both ready?"
    ),
    (2, 11, 101): "W-wait! We haven't finished talking!",
    (2, 11, 102): (
        "I'll be fine! Once I stop Armamon, I'll come right back. See you!"
    ),
    (2, 11, 103): (
        "It's okay. Taiki, Shoutmon, Dynasmon--everyone made me strong. "
        "This will work. Thank you, everyone. Now it's my turn to save you."
    ),
    (2, 11, 104): "Taiki! Shoutmon!",
    (2, 11, 105): "...Akari? What happened to me...?",
    (2, 11, 106): "Shoutmon! Are you okay?!",
    (2, 11, 107): "He's only unconscious. The damage is minimal.",
    (2, 11, 108): "Come on, brother! Wake up!",
    (2, 11, 109): "Huh?! Why is everyone gathered around? Did something happen?!",
    (2, 11, 110): "Correction: Ballistamon detects no damage whatsoever.",
    (2, 11, 111): "Those nerves of steel are incredible, brother!",
    (2, 11, 112): (
        "Taiki, what happened? There was a violent shaking and a huge explosion somewhere. "
        "Then the two of you suddenly appeared."
    ),
    (2, 11, 113): (
        "It wasn't a normal transfer. It looked like you were violently thrown out of somewhere."
    ),
    (2, 11, 114): "Thrown out...?",
    (2, 11, 115): "Taiki, did something happen to Spadamon?!",
    (2, 11, 116): (
        "Everyone, a miracle happened! The data distortion spreading from Lost Space vanished. "
        "It disappeared right after Taiki returned. Was this your doing?"
    ),
    (2, 11, 117): "...It was Spadamon.",
    (2, 11, 118): "...What?",
    (2, 11, 119): "Where is Spadamon?",
    (2, 11, 120): "That's right. Only Taiki and Shoutmon appeared. What happened to him?",
    (2, 11, 121): "Spadamon probably isn't coming back...",
    (2, 11, 122): (
        "He stayed behind in Lost Space alone to stop the gigantic Weapon Digimon's rampage."
    ),
    (2, 11, 123): "That idiot... S-Spadamon...!",
    (2, 11, 124): "Phew! Made it out just in time!",
    (2, 11, 125): "Spadaaaamon!",
    (2, 11, 126): "What?",
    (2, 11, 127): "...No way.",
    (2, 11, 128): "Spadamon! You're safe! We were worried sick!",
    (2, 11, 129): "Indeed. Shoutmon was on the verge of crying--",
    (2, 11, 130): "Shut up, Ballistamon! Don't tell them that!",
    (2, 11, 131): "Spadamon, are you really okay?",
    (2, 11, 132): "Yeah. It was close, but I escaped at the last second.",
    (2, 11, 133): (
        "Everyone is safe now! Armamon vanished along with the black hole. "
        "I think he returned to the same place as Dynasmon."
    ),
    (2, 11, 134): "What happened to Lost Space?",
    (2, 11, 135): (
        "Lost Space itself should now be accessible like any other area. I sealed the dangerous portion completely. "
        "There's still much we don't understand, so I'll observe it for a while before deciding what to do."
    ),
    (2, 11, 136): "Spadamon, you've changed. You suddenly sound dependable!",
    (2, 11, 137): (
        "W-well, that's thanks to my training! You were a real crybaby when we met. "
        "You're a man now, so don't cry again!"
    ),
    (2, 11, 138): "Thanks, Shoutmon. Now wipe away your own tears, okay?",
    (2, 11, 139): (
        "You did wonderfully, Spadamon. Everyone told me you're the last surviving Weapon Digimon. "
        "I always knew there was something special about you!"
    ),
    (2, 11, 140): (
        "What will you do now, Spadamon? Armamon and Dynasmon are both gone."
    ),
    (2, 11, 141): (
        "I've decided to protect the El Estou Zone as its last Weapon Digimon. "
        "Taiki, will you become my warrior?"
    ),
    (2, 11, 142): "Your warrior?",
    (2, 11, 143): (
        "When a Weapon Digimon finds someone worthy of all its power, it asks that person to become its warrior. "
        "I'll be your sword. This is the proof."
    ),
    (2, 11, 144): "Whoa! Taiki, is that...?",
    (2, 11, 145): "A Code Crown?!",
    (2, 11, 146): (
        "Yes. The Code Crown is granted to the master of the El Estou Zone--the one I should serve."
    ),
    (2, 11, 147): "All right! We got the Code Crown!",
    (2, 11, 148): "Obtained an important item: Code Crown!",
    (2, 11, 149): "Obtained equipment: LS Sword!",
    (2, 11, 150): "Obtained equipment: LS Shield!",
    (2, 11, 151): "Oh no... You accepted it...",
    (2, 11, 152): "Was I not supposed to?",
    (2, 11, 153): "It's not bad, but... are you sure, Taiki?",
    (2, 11, 154): "Sure about what?!",
    (2, 11, 155): "Spadamon, explain this properly!",
    (2, 11, 156): "Hehe! I was so happy that I explained things out of order.",
    (2, 11, 157): "So what does it mean?",
    (2, 11, 158): (
        "Whoever accepts this Code Crown must train the Weapon Digimon until it's strong enough to defend the Zone. "
        "Until then, you can't leave!"
    ),
    (2, 11, 159): "Whaaaat?!",
    (2, 11, 160): (
        "Don't worry! I'm already pretty strong, so it shouldn't take long. "
        "Everyone, I look forward to staying with you!"
    ),
    (2, 11, 161): (
        "I don't mind. I like Skyfort, and there are still areas we haven't explored."
    ),
    (2, 11, 162): (
        "Then I want to visit Earthfort! A gigantic machine's secret base--that's every man's dream!"
    ),
    (2, 11, 163): (
        "That sounds fun. Let's stay and support this Zone's Digimon for a while!"
    ),
    (2, 11, 164): "All right, Spadamon! Prepare for some serious training!",
    (2, 11, 165): "Enter Lost Space?",
    (2, 11, 166): "Yes, enter.",
    (2, 11, 167): "No, don't enter.",
    (2, 11, 168): "Return to Sky Garden?",
    (2, 11, 169): "Yes, return.",
    (2, 11, 170): "No, stay here.",
    (2, 11, 171): "Taiki! Are you okay?!",
    (2, 11, 172): "...Shoutmon? Y-yeah. I think I'm all right.",
    (2, 11, 173): (
        "I thought lightning struck in front of me. Then everything went dark. "
        "What happened to Barbamon and Kiriha?"
    ),
    (2, 11, 174): "Barbamon sent Kiriha to another Zone. Damn it... I couldn't stop him!",
    (2, 11, 175): (
        "It isn't only your fault. Barbamon deliberately spared us. He was mocking us!"
    ),
    (2, 11, 176): "We need to contact Patamon. Barbamon may be heading for Skyfort.",
    (2, 11, 177): "There you are! Everyone, this is terrible!",
    (2, 11, 178): "Parrotmon! Thank goodness the flight squad is safe!",
    (2, 11, 179): (
        "We're not safe! ROG invaded the City, forced everyone out, and occupied the Tower. "
        "A crackling barrier surrounds Skyfort, so we can't even approach!"
    ),
    (2, 11, 180): "What?! Zenjirou, Akari, and everyone else are still aboard Skyfort!",
    (2, 11, 181): (
        "That crackling barrier must be the Protection Field, Skyfort's defensive shield."
    ),
    (2, 11, 182): "Then they're safe! Patamon must have activated it, right?",
    (2, 11, 183): (
        "But it only works when every Capacitor Tower enters Emergency Mode. If the Towers were occupied..."
    ),
    (2, 11, 184): "Then Barbamon controls Skyfort!",
    (2, 11, 185): "You're safe, Team Xros Heart.",
    (2, 11, 186): "So Kiriha was sent away...",
    (2, 11, 187): "MailBirdramon?! Greymon too--you're safe?",
    (2, 11, 188): (
        "Kiriha found an opening to reload us. He ordered us to help you if anything happened to him."
    ),
    (2, 11, 189): (
        "We tracked ROG from the beginning and nearly solved this Zone's mystery. "
        "But we never imagined Barbamon was controlling ROG from the shadows."
    ),
    (2, 11, 190): "What will you do now?",
    (2, 11, 191): (
        "We just told you: we'll help. Barbamon's Shadow Guards took the Towers, "
        "and you'll need more fighting strength. We'll lend you ours."
    ),
    (2, 11, 192): "...We're glad, but...",
    (2, 11, 193): "Are you really okay with that?",
    (2, 11, 194): "Don't misunderstand. We follow Kiriha's orders.",
    (2, 11, 195): "That wording still rubs me the wrong way!",
    (2, 11, 196): "Until Kiriha returns to this Zone, we'll support you.",
    (2, 11, 197): (
        "Thanks, both of you. Kiriha must be safe. He isn't someone who goes down easily."
    ),
    (2, 11, 198): "Kiriha respects you.",
    (2, 11, 199): "Don't disappoint him.",
    (2, 12, 0): (
        "...Understood. MailBirdramon, Greymon--let's defeat Barbamon together."
    ),
    (2, 12, 1): "...Taiki.",
    (2, 12, 2): (
        "We'll defeat Barbamon and restore peace to this Zone. We need their power to do it."
    ),
    (2, 12, 3): (
        "You truly are Kiriha's rival. We'll remain nearby. Call whenever you need us."
    ),
    (2, 12, 4): (
        "I brought Penmon from the Item Shop. There's an Airport ahead, and Tentomon installed DigiLab "
        "and DigiFarm PCs in the tent. I'll support you too, so ask if you need anything!"
    ),
    (2, 12, 5): "Taiki, Shoutmon, can I explain how to return to Skyfort?",
    (2, 12, 6): "You know how?",
    (2, 12, 7): (
        "The Protection Field appears when all Capacitor Towers enter Emergency Mode. "
        "Return them all to Normal Mode, and we should be able to reach Skyfort."
    ),
    (2, 12, 8): "So we need to revisit every Tower we activated.",
    (2, 12, 9): (
        "If Barbamon releases Armamon, he could control the entire Digital World--perhaps your world too."
    ),
    (2, 12, 10): "The Weapon Digimon is really that powerful?",
    (2, 12, 11): (
        "Spadamon still lacks some memories. I wish we knew what Armamon is and why it was sealed."
    ),
    (2, 12, 12): "And I wish I could remember Dynasmon...",
    (2, 12, 13): "For now, retaking the Towers is our top priority!",
    (2, 12, 14): (
        "The Shadow Guards must be powerful. We should check the DigiLab and DigiFarm first. Let's go!"
    ),
    (2, 12, 15): "Thank you for reclaiming the Towers! You're incredible!",
    (2, 12, 16): "Then Skyfort's Protection-whatever is gone, right?!",
    (2, 12, 17): "No! There's one more Capacitor System we must shut down!",
    (2, 12, 18): "What?!",
    (2, 12, 19): (
        "The moment Spadamon returned the sixth Tower to Normal Mode, Earthfort received a transmission from another system."
    ),
    (2, 12, 20): "What did it say?!",
    (2, 12, 21): "Only that we should come to Stealth Valley.",
    (2, 12, 22): "There were six Towers but seven systems. Spadamon's memory was right.",
    (2, 12, 23): "But who manages the seventh system? Somebody must have sent that message.",
    (2, 12, 24): (
        "How was it hidden from ROG and erased from the map? Only an incredibly intelligent Digimon could rewrite Zone data."
    ),
    (2, 12, 25): "It could be another Barbamon trap.",
    (2, 12, 26): (
        "Maybe, but the voice was calm and powerful. It made me nervous without even sounding angry."
    ),
    (2, 12, 27): "It specifically asked Taiki's team to come too.",
    (2, 12, 28): "It knows about us...",
    (2, 12, 29): "I found Stealth Valley's port. You can fly there whenever you're ready!",
    (2, 12, 30): "Spadamon, wasn't Dynasmon the administrator of the Capacitor Systems?",
    (2, 12, 31): (
        "Dynasmon protected the Zone beside the Weapon Digimon. Is he calling us? "
        "Why would he hide in Stealth Valley instead of defending the Zone?"
    ),
    (2, 12, 32): "There must be a reason. Let's hurry to Stealth Valley!",
    (2, 12, 33): "Then what about Kiriha? Can you find where Barbamon sent him?",
    (2, 12, 34): "You're finally back! Listen--this is serious!",
    (2, 12, 35): "What's wrong? The Protection-whatever will disappear properly. Relax!",
    (2, 12, 36): "I know. I trust you completely!",
    (2, 12, 37): "Then why are you panicking?",
})

# Batch 1 quality-audit corrections in blocks 1 and 2.
_rog_explanation = (
    "ROG? 'Rogue'?\nWait, as in ROGUE?\nThat's English for\nan outlaw or thief,\nright?\nTalk about fitting.\n...\nAnd we didn't come\nto this Zone by\nchoice!\nEveryone mocked us,\nthen dragged us here\nbefore we could even\nget a word in!\nWe're the ones who\nwant answers!\nWhat's going on?!"
)
OVERRIDES.update({
    (2, 1, 82): _rog_explanation,
    (2, 1, 194): (
        "Hand that Digimon\nover to me.\nThe hidden power of\nL-Esta Zone belongs\nto no one else."
    ),
    (2, 1, 197): (
        "...\nWho are you people?\nDon't speak to me\nlike we're friends."
    ),
    (2, 2, 25): (
        "No other Digimon\nor humans nearby.\nForget that--we need\nto find Akari and\nthe others!"
    ),
    (2, 2, 28): _rog_explanation,
})

# Skyport activation, preview ending, and duplicated full-version introduction.
OVERRIDES.update({
    (2, 0, 161): (
        "Once the gate is\nopen, talk to a\nFlying Digimon.\nIt can take you to\nany Skyport you've\nalready unlocked."
    ),
    (2, 0, 162): "That's incredible!",
    (2, 0, 163): (
        "But... there's one\nproblem.\nI can't open this\ngate right now.\nSorry, Taiki."
    ),
    (2, 0, 164): (
        "Oh... well, we'll\nfigure it out."
    ),
    (2, 0, 165): (
        "Is this some kind\nof airport?"
    ),
    (2, 0, 166): (
        "Exactly. Flying\nDigimon use this\nfacility to carry\ntravelers.\nIt's called a\nSkyport."
    ),
    (2, 0, 167): (
        "Activate the switch\non that control\npanel..."
    ),
    (2, 0, 168): (
        "The gate will open,\nletting you travel\nto other Skyports.\nL-Esta Zone includes\nFort Island, Crystal\nIsland, and rugged\nHyde Island."
    ),
    (2, 0, 169): (
        "Open each island's\ngate first.\nAfter that, just\ntalk to a Flying\nDigimon whenever\nyou want to travel."
    ),
    (2, 0, 170): (
        "Perfect! Now we can\nfinally reach the\ncaptured Digimon!"
    ),
    (2, 0, 171): (
        "Taiki... do you\nreally think I can\nsave my friends?"
    ),
    (2, 0, 172): (
        "I know you can.\nAnd you won't be\ndoing it alone.\nWe're all with you!"
    ),
    (2, 0, 173): (
        "That's the end of\nthis preview!\nThanks for playing!"
    ),
    (2, 0, 174): (
        "But the real\nadventure is only\ngetting started!"
    ),
    (2, 0, 175): (
        "Check out the full\ngame and the TV\nanime!"
    ),
    (2, 0, 176): (
        "Thanks for all your\nsupport!\nSee you again!"
    ),
    (2, 0, 177): (
        "That's the end of\nthis preview!\nThanks for playing!"
    ),
    (2, 0, 178): (
        "But the real\nadventure is only\ngetting started!"
    ),
    (2, 0, 179): (
        "Check out the full\ngame and the TV\nanime!"
    ),
    (2, 0, 180): (
        "Thanks for all your\nsupport!\nSee you again!"
    ),
    (2, 0, 181): (
        "What's this?\nIt says:\n'DigiTent Save PC--\nPreparing'..."
    ),
    (2, 0, 182): (
        "It'll save your\nprogress eventually,\nbut it isn't ready\nyet."
    ),
    (2, 0, 183): "Hey, everybody!\nNice to meet you!",
    (2, 0, 184): "Nice to meet you!",
    (2, 0, 185): (
        "Before we begin,\nlet's meet the crew!"
    ),
    (2, 0, 186): OVERRIDES[(2, 0, 3)],
    (2, 0, 187): OVERRIDES[(2, 0, 4)],
    (2, 0, 188): OVERRIDES[(2, 0, 5)],
    (2, 0, 189): OVERRIDES[(2, 0, 6)],
    (2, 0, 190): OVERRIDES[(2, 0, 7)],
    (2, 0, 191): OVERRIDES[(2, 0, 8)],
    (2, 0, 192): OVERRIDES[(2, 0, 9)],
    (2, 0, 193): OVERRIDES[(2, 0, 10)],
    (2, 0, 194): OVERRIDES[(2, 0, 11)],
    (2, 0, 195): (
        "Tiny, lively, and\nalways together:\nthe Pickmons!"
    ),
    (2, 0, 196): (
        "When they combine\nwith Starmon, they\nform the Star Sword!"
    ),
    (2, 0, 197): OVERRIDES[(2, 0, 14)],
    (2, 0, 198): OVERRIDES[(2, 0, 15)],
    (2, 0, 199): OVERRIDES[(2, 0, 16)],
})

# Sky Fort facilities: Tent, DigiFarm, DigiLab, and Skyport tutorials.
OVERRIDES.update({
    (2, 0, 121): "Taiki, know how\nto open a Tent?",
    (2, 0, 122): (
        "See the Tent icon\nright there?"
    ),
    (2, 0, 123): (
        "Stand on the Tent\nicon and press A\nto set it up.\nInside, you can\nrestore HP and MP\nand save your\nadventure."
    ),
    (2, 0, 124): (
        "Got it... except\nI don't own a Tent."
    ),
    (2, 0, 125): (
        "Once we reclaim\nFort Island, I can\nmake as many as we\nneed.\nFor now, don't worry.\nYou won't need one\nright away."
    ),
    (2, 0, 126): (
        "This is where you\nmanage the DigiFarm."
    ),
    (2, 0, 127): (
        "The DigiFarm?\nWhat's that?"
    ),
    (2, 0, 128): (
        "It's where Digimon\nyou've befriended\ncan train and grow."
    ),
    (2, 0, 129): (
        "Each DigiFarm can\nhold six Digimon,\nand you can befriend\nup to forty total.\nFarm Digimon can\nchat, train, work,\nor explore.\nThey'll gain stats,\nfind items, and even\nmake useful supplies.\nYou can freely move\nDigimon between the\nparty, farms, and\nDigiBank."
    ),
    (2, 0, 130): (
        "How do we expand\nthe DigiFarm?"
    ),
    (2, 0, 131): (
        "Six Capacitor\nTowers send power\nto Sky Fort.\nActivate a tower's\ngenerator and Sky\nFort will expand,\nunlocking another\nDigiFarm.\nSo power up every\ntower you find!"
    ),
    (2, 0, 132): (
        "Did someone explain\nthe DigiFarm yet?"
    ),
    (2, 0, 133): (
        "It helps our\nDigimon grow faster,\nright?"
    ),
    (2, 0, 134): (
        "Exactly! Smart use\nof the DigiFarm is\nthe key to raising\na strong team."
    ),
    (2, 0, 135): (
        "Farm Digimon gain\nEXP over time, but\nthat's only the\nstart.\nChat and Training\nraise their stats.\nWork can produce\nrare items.\nExploration gathers\nitems from the Zone."
    ),
    (2, 0, 136): (
        "Wow... the DigiFarm\ncan do all that?"
    ),
    (2, 0, 137): (
        "It's essential for\nbringing out a\nDigimon's full power.\nWe should activate\nthose Capacitor\nTowers."
    ),
    (2, 0, 138): (
        "This is the DigiLab."
    ),
    (2, 0, 139): (
        "The DigiLab?\nWhat's it for?"
    ),
    (2, 0, 140): (
        "It's where you can\ncreate and manage\nDigimon."
    ),
    (2, 0, 141): (
        "You can turn battle\nMelodies into new\nDigimon, complete\nDigiScores, and use\nFusion to create\nentirely new forms."
    ),
    (2, 0, 142): "What's a Melody?",
    (2, 0, 143): (
        "A Melody is a\nDigimon converted\ninto data.\nDefeat an enemy in\none blow--or finish\nit with a Melody-\neffect skill--and\nit may become a\nMelody stored in\nyour Xros Loader."
    ),
    (2, 0, 144): (
        "Then what's a\nDigiScore?"
    ),
    (2, 0, 145): (
        "A DigiScore is a\nblueprint showing\nwhich Melodies are\nneeded to create a\nspecific Digimon.\nOrange DigiScores\nare incomplete.\nFill their empty\nslots with the right\nMelodies before you\ncan read them."
    ),
    (2, 0, 146): (
        "And what did you\nmean by Fusion?"
    ),
    (2, 0, 147): (
        "Fusion is a special\nprocess available\nonly at Sky Fort."
    ),
    (2, 0, 148): (
        "Collect Melodies,\ncomplete a DigiScore,\nthen use DigiCoding\nto create its\nDigimon.\nSome creations also\nrequire enough BIT,\na certain level, or\nother conditions."
    ),
    (2, 0, 149): (
        "Okay. What's\nDigiCoding?"
    ),
    (2, 0, 150): (
        "DigiCoding combines\nMelodies collected\nin battle and turns\nthem into a Digimon.\nFinish an enemy in\none blow or with a\nMelody-effect skill\nto improve your odds\nof collecting its\nMelody."
    ),
    (2, 0, 151): (
        "Got it. Thanks for\nexplaining,\nSpadamon!"
    ),
    (2, 0, 152): (
        "So the DigiLab is\nwhere we manage our\nDigimon?"
    ),
    (2, 0, 153): (
        "Right.\nUse DigiCompose to\ncomplete DigiScores.\nUse DigiCoding to\ncreate Digimon from\nMelodies.\nFusion creates new\nDigimon from existing\nones.\nThe Digimon List\nshows details for\nevery Digimon you've\nencountered."
    ),
    (2, 0, 154): (
        "What's this?\nIt says:\n'Command Room Save\nPC--Preparing'..."
    ),
    (2, 0, 155): (
        "It'll save your\nprogress someday,\nbut it isn't ready\nyet."
    ),
    (2, 0, 156): (
        "Figures. Nothing's\never that easy."
    ),
    (2, 0, 157): (
        "Maybe it'll award\nBIT too!\nLet's see...\n.........\nNope. I'm broke."
    ),
    (2, 0, 158): "What's this place?",
    (2, 0, 159): (
        "This is the Skyport.\nFlying Digimon carry\npassengers between\nislands.\nUse that control\npanel to open the\ngate."
    ),
    (2, 0, 160): (
        "Once a Skyport is\nactive, you can fly\nto other unlocked\nports.\nL-Esta Zone includes\nFort Island, volcanic\nCrystal Island, and\nthe rugged Hyde\nIsland to the north\nand south."
    ),
})

# Formation tutorial, Spadamon reunion, and central-room confrontation.
OVERRIDES.update({
    (2, 0, 81): "After you sent him\nflying like that...?",
    (2, 0, 82): (
        "Sh-shut up!\nSilence, weaklings!\nYou haven't seen\nwhat I'm really\ncapable of!\nNow I'll show you\ntrue terror!"
    ),
    (2, 0, 83): (
        "That is some truly\nterrifying whining."
    ),
    (2, 0, 84): (
        "We're used to\nstubborn enemies.\nIf you won't quit,\nwe'll beat you as\nmany times as it\ntakes!"
    ),
    (2, 0, 85): (
        "Good formations\ncan turn a battle.\nThe Digimon in the\ncenter is your\nVanguard.\nIt deals full damage\nand can use Fusion\nTechniques."
    ),
    (2, 0, 86): (
        "Digimon supporting\nthe Vanguard are\nRear Guards.\nTheir direct attacks\ndeal half damage,\nand they can't use\nFusion Techniques.\nIn exchange, enemies\ncan't target them.\nYou need a Vanguard\nbefore assigning\nRear Guards."
    ),
    (2, 0, 87): (
        "Move the cursor\nwith the D-Pad.\nHighlight a Digimon\nand press A to open\nits Command Ring."
    ),
    (2, 0, 88): (
        "When every Digimon\nhas its orders,\npress X.\nAll selected commands\nwill be carried out!"
    ),
    (2, 0, 89): (
        "Want to hear that\nagain?"
    ),
    (2, 0, 90): "Explain it again.",
    (2, 0, 91): "Start the battle.",
    (2, 0, 92): (
        "All right, team!\nLet's try this again!\nDigiXros!!"
    ),
    (2, 0, 93): (
        "Spadamon! Thank\ngoodness you're safe!"
    ),
    (2, 0, 94): (
        "Sorry I'm late.\nI left everyone\nbehind and hid all\nby myself...\nI'm so sorry."
    ),
    (2, 0, 95): (
        "What're you talking\nabout? You did the\nright thing!\nIf they captured\nyou too, this Zone\nwould be finished!"
    ),
    (2, 0, 96): "What do you mean?",
    (2, 0, 97): (
        "Spadamon isn't an\nordinary Digimon.\nHe's a Weapon\nDigimon--the guardian\nof this Zone.\nA tremendous power\nrests inside him.\nWe can't let the\nenemy take it!"
    ),
    (2, 0, 98): (
        "Spadamon's some\nkind of god?!"
    ),
    (2, 0, 99): (
        "N-no, nothing that\ndramatic!\nI was created to\nprotect this Zone,\nbut I can't defeat\nan invading army\nalone.\nMy role is to find\nallies, bring them\ntogether, and guide\nthem.\nThat's all."
    ),
    (2, 0, 100): (
        "Right! Speaking of\nallies, where are\nour friends?"
    ),
    (2, 0, 101): (
        "They were taken to\nthe central room.\nBut be careful.\nThe Digimon in there\nis scary...\nin a weird sort of\nway."
    ),
    (2, 0, 102): (
        "Okay, I have to\nask. What does\n'scary in a weird\nway' mean?"
    ),
    (2, 0, 103): (
        "I peeked inside\nonce.\nHe was laughing like\nhe'd heard the best\njoke ever.\nThen he started\nscreaming in rage...\nand finally burst\ninto tears.\nBut when I looked\ncloser, he was doing\nall of it alone."
    ),
    (2, 0, 104): (
        "So not scary.\nJust dangerous."
    ),
    (2, 0, 105): "You're the boss!",
    (2, 0, 106): (
        "...Who are you?\nWho gave you\npermission to enter\nthis room?\nGet out!"
    ),
    (2, 0, 107): (
        "We're not leaving!\nYou're the ones who\nneed to go!\nThis room, this fort,\nand this whole Zone\nbelong to us!\nWe won't hand them\nover!"
    ),
    (2, 0, 108): (
        "Ah... I remember\nyou.\nThe coward who ran\nand abandoned his\nfriends.\nYou've returned with\nanother pitiful\nlittle group.\nWhat do you intend\nto accomplish?"
    ),
    (2, 0, 109): (
        "Isn't it obvious?\nWe're gonna send\nyou creeps flying!"
    ),
    (2, 0, 110): (
        "Then we'll take\nback our friends\nand this Zone!"
    ),
    (2, 0, 111): (
        "Miserable fools.\nDie regretting your\nown stupidity."
    ),
    (2, 0, 112): (
        "Keep spouting those\ncheap villain lines.\nEverybody who heard\nyou talk like that\nbefore us went home\nin one piece!"
    ),
    (2, 0, 113): (
        "Your scheme ends\nright here!\nGive up and get out\nof this Zone!"
    ),
    (2, 0, 114): (
        "...I see. You're\nexceptionally foolish."
    ),
    (2, 0, 115): "What'd you say?!",
    (2, 0, 116): (
        "Soon you'll grasp\nthe depth of your\nmistake.\nBut by the time you\ndo, everything will\nalready be too late."
    ),
    (2, 0, 117): (
        "...What's that\nsupposed to mean?"
    ),
    (2, 0, 118): (
        "Part of Spadamon's\npower has returned!"
    ),
    (2, 0, 119): (
        "You defeated the\nDigimon maintaining\none of my seals.\nPart of the power\nheld inside me is\nfree again.\nThank you, everyone!"
    ),
    (2, 0, 120): (
        "So this is the\npower of the Weapon\nDigimon guarding\nL-Esta Zone...\nIf we break every\nseal, can we restore\nall of it?"
    ),
})

# Guards, rescue decision, Spadamon confrontation, and first battle.
OVERRIDES.update({
    (2, 0, 40): (
        "Stupid jerks had\nto build such a\ncomplicated door.\nI've twisted every\nthing I can find,\nand it still won't\nopen!\nSo I'm the only one\nstuck playing jailer!"
    ),
    (2, 0, 41): "Shoutmon!\nYou okay?!",
    (2, 0, 42): (
        "Not like you can\nescape, but listen\nup!\nTry anything funny\nand your buddies\npay the price!"
    ),
    (2, 0, 43): "Shoutmon!\nCan you hear me?!",
    (2, 0, 44): "Come on, wake up!\nShoutmon!",
    (2, 0, 45): "Shoutmon!!",
    (2, 0, 46): (
        "...Taiki!\nWe've got trouble!\nThey hauled\nSparrowmon and the\nothers someplace\nelse.\nThose creeps are up\nto something!"
    ),
    (2, 0, 47): "...What?!",
    (2, 0, 48): (
        "Huh? You're the\nDigimon who called\nus here.\nThought you escaped."
    ),
    (2, 0, 49): (
        "I did. My friends\nhelped me get out.\nThey always do.\n...Taiki, I need to\nask you something."
    ),
    (2, 0, 50): (
        "I want to save\nevery prisoner--\nyour friends and\nmine.\nPlease... will you\nhelp me?"
    ),
    (2, 0, 51): "Of course we will!",
    (2, 0, 52): "Now that's what I\nwanted to hear!",
    (2, 0, 53): (
        "First, we need a\nway through this\ndoor."
    ),
    (2, 0, 54): (
        "Easy--if you don't\nmind making noise.\nBefore the invaders\nstole this place,\nit belonged to us."
    ),
    (2, 0, 55): (
        "Then let's move,\nTaiki!\nI'm gonna blast\nthose creeps!"
    ),
    (2, 0, 56): (
        "We heard this Zone\nis hiding something.\nWhat is it?\nSpit it out!"
    ),
    (2, 0, 57): (
        "I-I don't know!\nWhy would they tell\na grunt like me?!"
    ),
    (2, 0, 58): (
        "Then you're useless.\nLet's toss you out\nand see if you can\nfly!"
    ),
    (2, 0, 59): "Stop right there!",
    (2, 0, 60): (
        "D-don't touch my\nfriends!\nI won't let you!"
    ),
    (2, 0, 61): (
        "Hah! Your voice is\nshaking.\nYou're the coward\nwho survived, huh?"
    ),
    (2, 0, 62): (
        "You ran while your\nfriends got crushed.\nGonna hide behind\nthese humans now?"
    ),
    (2, 0, 63): (
        "I won't run again!\nAnd I won't use\nanyone as a shield!\nI'll beat you and\nsave everybody!\nTaiki! Shoutmon!\nPlease fight with\nme!"
    ),
    (2, 0, 64): (
        "You got it,\nSpadamon!\nTaiki's our General.\nNobody brings out\na Digimon's power\nlike he does!\nRight, Taiki?"
    ),
    (2, 0, 77): (
        "Okay, everyone!\nLet's do this!\nDigiXros!!"
    ),
    (2, 0, 78): "Yeah! We did it!",
    (2, 0, 79): (
        "You pulled it off!\nThat was awesome,\nTaiki!\nI knew you were\nthe right General!"
    ),
    (2, 0, 80): (
        "Heh. Not bad.\nBut don't get cocky!\nThat was only a\ntest.\nI played weak just\nto size you up!"
    ),
})


PLAIN_REPLACEMENTS = (
    ("Kudou Taiki", "Taiki Kudo"),
    ("Kudo Taiki", "Taiki Kudo"),
    ("Hinomoto Akari", "Akari Hinomoto"),
    ("Tsurugi Zenjirou", "Zenjirou Tsurugi"),
    ("Aonuma Kiriha", "Kiriha Aonuma"),
    ("Cross Heart", "Xros Heart"),
    ("Digi Cross", "DigiXros"),
    ("Digi-Cross", "DigiXros"),
    ("Cross Loader", "Xros Loader"),
    ("Shout Mon", "Shoutmon"),
    ("Ballista Mon", "Ballistamon"),
    ("Doruru Mon", "Dorulumon"),
    ("Cutie Mon", "Cutemon"),
    ("Spada Mon", "Spadamon"),
    ('"Meirei" command', "Orders command"),
    ('"Sakusen" command', "Strategy command"),
    ('"Soubi"', '"Equipment"'),
    ("Digi cloth", "DigiXros"),
    ("Digicloth", "DigiXros"),
    ("Melody Kouka", "DigiMelody effect"),
    ("melodyization", "DigiMelody conversion"),
)


# Batch 2X: global prose records 2438-2592 (2,007 draft-English words).
OVERRIDES.update({
    (2, 12, 38): "Listen! Lost Space suddenly appeared near Sky Fort!",
    (2, 12, 39): "What?!",
    (2, 12, 40): "If you need a flying Digimon, I'm ready. Head for Sky Fort as soon as you're prepared!",
    (2, 12, 41): "W-what do we do, Taiki?!",
    (2, 12, 42): "I'm worried about Akari, Zenjirou, and everyone else!",
    (2, 12, 43): "Let's hurry back to Sky Fort!",
    (2, 12, 44): "Thanks, Parrotmon. You've been a huge help.",
    (2, 12, 45): "I'll wait here. Come see me anytime you need a ride!",
    (2, 12, 46): "Taiki! You're back!",
    (2, 12, 47): "Thank goodness! I'm so relieved everyone made it back!",
    (2, 12, 48): "Akari, Zenjirou, Patamon... Great! Is everyone here? Nobody's missing?",
    (2, 12, 49): "Yeah. It was close, but we're all okay!",
    (2, 12, 50): "Not long after you left for Crystal Volcano...",
    (2, 12, 51): "Something appeared near Earth Fort. A huge shadow came racing toward us. Just before it arrived, a crackling barrier suddenly formed around Sky Fort.",
    (2, 12, 52): "The barrier kept that shadow out, but it trapped us inside too.",
    (2, 12, 53): "Then the barrier suddenly vanished, and that shadow came back!",
    (2, 12, 54): "I'm certain that shadow was Barbamon!",
    (2, 12, 55): "Barbamon? Is that a Digimon?",
    (2, 12, 56): "A terrifying one! ROG and everything else that's happened were all Barbamon's doing!",
    (2, 12, 57): "But the shadow ignored us completely. At least, that's how it seemed.",
    (2, 12, 58): "Seriously?",
    (2, 12, 59): "Yeah. It shot right past us at incredible speed.",
    (2, 12, 60): "I'm sure of it. It was headed for the Sky Garden!",
    (2, 12, 61): "The Sky Garden? There wasn't anything there, was there?",
    (2, 12, 62): "No. If anything is there now, it has to be trouble.",
    (2, 12, 63): "We won't know until we look. Come on, Taiki!",
    (2, 12, 64): "Right! Let's go!",
    (2, 12, 65): "What should we do?",
    (2, 12, 66): "The Digimon who hid from ROG may start returning. Stay here and watch over Sky Fort!",
    (2, 12, 67): "Thanks!",
    (2, 12, 68): "All right! I'll support you from here too!",
    (2, 12, 69): "Why are Akari and the others so worked up? Everything turned out fine!",
    (2, 12, 70): "For now, I'm just glad everyone's safe. All that's left is stopping Armamon's revival!",
    (2, 12, 71): "Finally! I was getting bored waiting around while you slept!",
    (2, 12, 72): "Did somebody else show up?",
    (2, 12, 73): "Well... sort of. While I was having a little fun, Taiki's fans stormed in and turned Sky Fort upside down!",
    (2, 12, 74): "Fans? Mine?",
    (2, 12, 75): "Digimon who fled ROG came to meet the hero who saved the El Est Zone! You're famous, Taiki. Better start practicing your autograph!",
    (2, 12, 76): "Shoutmon's autograph is so messy nobody can read it. That's the real joke here.",
    (2, 12, 77): "What?! That's not funny, Zenjirou! You've been living it up here at Earth Fort, haven't you?!",
    (2, 12, 78): "Hey, Earth Fort is a man's... No, a warrior's romance!",
    (2, 12, 79): "Not everyone came just to meet Taiki. Some Digimon need your help. Check the Quest Monitor when you have time.",
    (2, 12, 80): "Got it. If they're counting on us, we'll help however we can!",
    (2, 12, 81): "Fans or not, the Zone is still dangerous. If you're heading out, I'm coming with you!",
    (2, 12, 82): "Then let's continue the legend of the Weapon Digimon!",
    (2, 12, 83): "Taiki! Come on, let's get going!",
    (2, 12, 84): "Rest here?",
    (2, 12, 85): "Yes, rest.",
    (2, 12, 86): "No, don't rest.",
    (2, 12, 87): "All Digimon's HP and MP were restored!",
    (2, 12, 88): "Rest here?",
    (2, 12, 89): "Yes, rest.",
    (2, 12, 90): "No, don't rest.",
    (2, 12, 91): "All Digimon's HP and MP were restored!",
    (2, 12, 92): "Leave the tent?",
    (2, 12, 93): "Yes, leave.",
    (2, 12, 94): "No, stay.",
    (2, 12, 95): "Ride a flying Digimon?",
    (2, 12, 96): "Yes, let's go.",
    (2, 12, 97): "No, not yet.",
    (2, 12, 98): "Whenever you're ready to leave, just talk to me.",
    (2, 12, 99): "Talk to me again when you want to go somewhere!",
    (2, 12, 100): "Ride a flying Digimon?",
    (2, 12, 101): "Yes, let's go.",
    (2, 12, 102): "No, not yet.",
    (2, 12, 103): "Whenever you're ready to leave, just talk to me.",
    (2, 12, 104): "Talk to me again when you want to go somewhere!",
    (2, 12, 105): "Obtained a consumable item!\n^i",
    (2, 12, 106): "Obtained consumable items!\n^i?@?~^n",
    (2, 12, 107): "Obtained an item!\n^i",
    (2, 12, 108): "Obtained items!\n^i??^n",
    (2, 12, 109): "Obtained a Melody!\n^0",
    (2, 12, 110): "Obtained Melodies!\n^0??^1",
    (2, 12, 111): "Obtained a Farm Good!\n^i",
    (2, 12, 112): "Obtained Farm Goods!\n^i?@?~^n",
    (2, 12, 113): "Obtained a DigiScore!\n^i",
    (2, 12, 114): "Obtained a key item!\n^i",
    (2, 12, 115): "Obtained ^b bits!",
    (2, 12, 116): "You don't have the key needed to open this gate!",
    (2, 12, 117): "The airport gate opened!",
    (2, 12, 118): "You don't have the key needed to open this gate!",
    (2, 12, 119): "The switch gate opened!",
    (2, 12, 120): "No Digimon in your party knows the Rock Break field skill.",
    (2, 12, 121): "Used the Rock Break field skill!",
    (2, 12, 122): "No Digimon in your party knows the Tree Cut field skill.",
    (2, 12, 123): "Used the Tree Cut field skill!",
    (2, 12, 124): "No Digimon in your party knows the Ice Melt field skill.",
    (2, 12, 125): "Used the Ice Melt field skill!",
    (2, 12, 126): "Use the Dig field skill?",
    (2, 12, 127): "Yes, use it.",
    (2, 12, 128): "No, don't use it.",
    (2, 12, 129): "No Digimon in your party knows the Dig field skill.",
    (2, 12, 130): "Used the Dig field skill!",
    (2, 12, 131): "Use the Scout field skill?",
    (2, 12, 132): "Yes, use it.",
    (2, 12, 133): "No, don't use it.",
    (2, 12, 134): "No Digimon in your party knows the Scout field skill.",
    (2, 12, 135): "Used the Scout field skill!",
    (2, 12, 136): "Why is there a monitor all the way out here?",
    (2, 12, 137): "This monitor explains battle commands.",
    (2, 12, 138): "It's a help monitor. We may as well hear what it has to say.",
    (2, 12, 139): "I want to keep moving, but listening now could save us trouble later.",
    (2, 12, 140): "You give commands to allied Digimon using the Touch Screen.",
    (2, 12, 141): "Select a Digimon to open its Command Ring on the Touch Screen. Choose a command, then press the A Button.",
    (2, 12, 142): "Choose Fight to attack without spending MP. Use it when you want to conserve MP.",
    (2, 12, 143): "Choose Move to use a special move. Some moves damage enemies, while others provide support. Exploit an enemy's weakness to deal extra damage.",
    (2, 12, 144): "Choose DigiXros to use a combination move. Every required Digimon must be in your party. DigiXros cannot be used if a required Digimon is suffering from paralysis, sleep, blindness, or another disabling condition.",
    (2, 12, 145): "Choose Item to use an item on a Digimon. Items can restore HP or MP, cure conditions such as paralysis, sleep, and blindness, or revive a fallen Digimon.",
    (2, 12, 146): "Choose Strategy to let a Digimon battle automatically. Full Power uses the strongest available attacks. Conserve saves MP. Guard focuses on defense. Escape attempts to flee. The battle continues if even one enemy blocks your escape.",
    (2, 12, 147): "Choose Formation to swap the selected Digimon with another party member.",
    (2, 12, 148): "Press the B Button to cancel and choose again.",
    (2, 12, 149): "When your commands are set, press the X Button to begin the turn.",
    (2, 12, 150): "I see... Shoutmon, did you get all that?",
    (2, 12, 151): "Not even a little! But General can handle the complicated stuff! We heard the monitor, so let's go find everyone!",
    (2, 12, 152): "Review the battle-command tutorial?",
    (2, 12, 153): "Yes, review it.",
    (2, 12, 154): "No, I'm good.",
    (2, 12, 155): "Listen to the explanation again?",
    (2, 12, 156): "This monitor explains how to set up a tent.",
    (2, 12, 157): "Want to learn how tents work?",
    (2, 12, 158): "First, find a Tent Point.",
    (2, 12, 159): "Press the A Button at a Tent Point to open your tent and enter it. Inside, you can restore HP and MP and save your game.",
    (2, 12, 160): "Tents are invaluable when you're in trouble, so remember how to use them.",
    (2, 12, 161): "There's a Tent Point right here. Let's try it.",
    (2, 12, 162): "Press the A Button at a Tent Point to open your tent. Inside, you can restore HP and MP and save your game.",
    (2, 12, 163): "Huh? Another monitor.",
    (2, 12, 164): "This monitor explains battle formations.",
    (2, 12, 165): "Formations sound kind of complicated...",
    (2, 12, 166): "They're not that hard. Let's hear it out.",
    (2, 12, 167): "Your battle formation determines each Digimon's role. Digimon at the front are the Vanguard. They shield the Digimon behind them and are the only ones able to perform DigiXros.",
    (2, 12, 168): "Digimon behind the Vanguard are the Rearguard. They are protected from enemy attacks, but deal less damage. If every Vanguard Digimon falls, the Rearguard moves forward. You must assign at least one Digimon to the Vanguard.",
    (2, 12, 169): "Use the +Control Pad to move the cursor. Select a Digimon and press the A Button to open its Command Ring.",
    (2, 12, 170): "Press the Y Button to switch a Digimon between the Vanguard and Rearguard.",
    (2, 12, 171): "The command list shows each Digimon's next action. Strategy displays the chosen plan; Move or DigiXros displays the move; Item displays the selected item.",
    (2, 12, 172): "Once every Digimon has an action, press the X Button.",
    (2, 12, 173): "Move, DigiXros, and Item apply to the next turn only. Strategy settings remain active: Full means Full Power, Eco means Conserve, Esc means Escape, and Grd means Guard. Every Digimon starts with Full Power, but you can change that setting through Strategy.",
    (2, 12, 174): "Assigning the right roles is the key to making battles easier.",
    (2, 12, 175): "Got it. So deciding everyone's role really matters?",
    (2, 12, 176): "Exactly! That's where our General gets to show what he can do!",
    (2, 12, 177): "Review the formation tutorial?",
    (2, 12, 178): "Assigning the right roles is the key to making battles easier.",
    (2, 12, 179): "Listen to the explanation again?",
    (2, 12, 180): "Why is there a monitor all the way out here?",
    (2, 12, 181): "This monitor explains battle commands.",
    (2, 12, 182): "It's a help monitor. We may as well hear what it has to say.",
    (2, 12, 183): "I want to keep moving, but listening now could save us trouble later.",
    (2, 12, 184): "I see... Shoutmon, did you get all that?",
    (2, 12, 185): "Not even a little! But General can handle the complicated stuff! We heard the monitor, so let's go find everyone!",
    (2, 12, 186): "Review the battle-command tutorial?",
    (2, 12, 187): "Listen to the explanation again?",
    (2, 12, 188): "This monitor explains how to set up a tent.",
    (2, 12, 189): "Want to learn how tents work?",
    (2, 12, 190): "First, find a Tent Point.",
    (2, 12, 191): "Press the A Button at a Tent Point to open your tent and enter it. Inside, you can restore HP and MP and save your game.",
    (2, 12, 192): "Tents are invaluable when you're in trouble, so remember how to use them.",
})

# Batch 2Y: global prose records 2593-2741 (2,011 draft-English words).
OVERRIDES.update({
    (2,12,193): "There's a Tent Point right here. Let's try it.",
    (2,12,194): "Press the A Button at a Tent Point to open your tent. Inside, you can restore HP and MP and save your game.",
    (2,12,195): "Huh? Another monitor.",
    (2,12,196): "This monitor explains battle formations.",
    (2,12,197): "Formations sound kind of complicated...",
    (2,12,198): "They're not that hard. Let's hear it out.",
    (2,12,199): "Assigning the right roles is the key to making battles easier.",
    (2,13,0): "Got it. So deciding everyone's role really matters?",
    (2,13,1): "Exactly! That's where our General gets to show what he can do!",
    (2,13,2): "Review the formation tutorial?",
    (2,13,3): "Assigning the right roles is the key to making battles easier.",
    (2,13,4): "Listen to the explanation again?",
    (2,13,5): "This door protects the Capacitor Tower's system. It's sealed tight. ROG never got inside, but something feels different from last time...",
    (2,13,6): "Whoa! What was that?! Taiki, did you do something?",
    (2,13,7): "No. Spadamon, did something happen?",
    (2,13,8): "I only touched it, and it clicked! The door still won't open, though...",
    (2,13,9): "Then maybe it reacted to Spadamon?",
    (2,13,10): "But why would it? It didn't react at all the last time you were here.",
    (2,13,11): "But...",
    (2,13,12): "Why are we standing around? Get the tower running before Sky Fort becomes unlivable!",
    (2,13,13): "He's right. Restoring the power comes first.",
    (2,13,14): "Spadamon, examine the tower.",
    (2,13,15): "O-okay...",
    (2,13,16): "Once this starts up, Sky Fort will regain power. We'll be able to use the DigiLab and DigiFarm too. I can't wait!",
    (2,13,17): "Sky Fort's systems came back online!",
    (2,13,18): "A new Farm Island was created!",
    (2,13,19): "Yes! It worked!",
    (2,13,20): "Nice work, Spadamon! But what's a Farm Island? Is it different from the DigiFarm Patamon mentioned?",
    (2,13,21): "Farm Islands are habitats inside the DigiFarm. Each island can raise up to eight Digimon. Farm Boards and BGM Boards change how Digimon develop, so customize each island to match your goals. First, name your new Farm Island!",
    (2,13,22): "Nice! That's the perfect name for our first Farm Island!",
    (2,13,23): "Does this mean all of Sky Fort is running again?",
    (2,13,24): "There are six Capacitor Towers, and we've only restored one. So Sky Fort is operating at about sixteen percent.",
    (2,13,25): "That's all?!",
    (2,13,26): "No need to rush. One step at a time. At least we aren't completely out of power anymore.",
    (2,13,27): "The restored power also unlocked part of the Data Library!",
    (2,13,28): "Obtained a DigiScore!\n~I",
    (2,13,29): "Obtained a DigiScore!\n~I",
    (2,13,30): "Obtained a DigiScore!\n~I",
    (2,13,31): "A DigiScore? What's that?",
    (2,13,32): "DigiScores are required for DigiFusion. You can perform DigiFusion at the DigiLab.",
    (2,13,33): "DigiFusion? What's that?",
    (2,13,34): "DigiFusion combines two Digimon to create a new one. Think of it as a special kind of DigiXros.",
    (2,13,35): "It combines them into a new Digimon?! That's incredible!",
    (2,13,36): "Sky Fort once stored every DigiScore in this Zone. When the power failed, most backups were destroyed, but you can recover DigiScores by defeating wild Digimon. Use the DigiLab PC and Farm PC here at Sky Fort.",
    (2,13,37): "Taiki! I heard something over there. Someone's coming!",
    (2,13,38): "Could it be ROG again?!",
    (2,13,39): "They couldn't have found us this quickly... could they?",
    (2,13,40): "Questions later! Let's check it out. Come on, Spadamon, keep up!",
    (2,13,41): "Huh? W-wait! I'm still trying to catch my breath!",
    (2,13,42): "Spadamon! And you... Humans? Now that's a rare sight.",
    (2,13,43): "Who are you?",
    (2,13,44): "I'm Ganimon. I used to live around here. When the Capacitor Tower suddenly started running, I hurried over. I'm not your enemy.",
    (2,13,45): "Don't scare us like that! We restored the tower. That's one down and five to go!",
    (2,13,46): "You restored it? I feared ROG had seized the tower at last. Thank you for saving it! If it responded, has Spadamon's memory returned?",
    (2,13,47): "Huh?! N-not yet. I don't even know why the door reacted to me.",
    (2,13,48): "I see. Don't force it. Your memories matter, but they'll return when the time is right. Until then, keep fighting and show everyone what you can do.",
    (2,13,49): "I have gotten a little stronger! I'll protect Sky Fort, Patamon, and everyone else... as best I can.",
    (2,13,50): "Well said, Spadamon. I knew you had it in you.",
    (2,13,51): "Thanks, Taiki.",
    (2,13,52): "I see you've chosen good friends. Taiki, please help Spadamon grow stronger. We'll do everything we can to support you. The Digimon returning here will make Sky Fort their home.",
    (2,13,53): "Listen to him acting all important. I was going to explain everything anyway!",
    (2,13,54): "Ask Tailmon over there if you want to learn about wireless communication.",
    (2,13,55): "Ask BomberNanimon about Farm Goods and changing the environment on a Farm Island.",
    (2,13,56): "Penmon runs the Item Shop.",
    (2,13,57): "Speak to Clockmon whenever you want to use a ticket.",
    (2,13,58): "The nearest Capacitor Tower is east of here. Go there next. Everyone here believes in you.",
    (2,13,59): "I've spent so long running away... Being depended on almost feels nice. W-what am I saying?! Back into the Xros Loader!",
    (2,13,60): "He's pretty fired up! I thought he was just shy, but Spadamon's actually a funny guy.",
    (2,13,61): "Give me a second. I'll open it.",
    (2,13,62): "I really am getting the hang of this...",
    (2,13,63): "Sky Fort's systems came back online!",
    (2,13,64): "A new Farm Island was created!",
    (2,13,65): "Please name this Farm Island.",
    (2,13,66): "Thanks, Taiki. Another great name! We also regained access to more DigiScores.",
    (2,13,67): "Obtained a DigiScore!\n~I",
    (2,13,68): "Obtained a DigiScore!\n~I",
    (2,13,69): "Obtained a DigiScore!\n~I",
    (2,13,70): "Now we can perform more DigiFusions! Still, getting the tower running was harder than I expected.",
    (2,13,71): "I-it can't be helped! I still don't understand how any of this works.",
    (2,13,72): "The tower is mysterious. How did you know how to operate that panel?",
    (2,13,73): "I don't really know. Somehow my hands knew what to do. Maybe it's connected to my memories?",
    (2,13,74): "Maybe. Just don't push yourself too hard.",
    (2,13,75): "I heard something outside again. Let's take a look.",
    (2,13,76): "Hanumon?! You came!",
    (2,13,77): "Hey, Spadamon! Ganimon told me, so I rushed over. Thanks for restoring the tower. This place finally feels like home again!",
    (2,13,78): "Is he another Digimon who lived here?",
    (2,13,79): "Yeah. Hanumon led the Digimon in this area. When ROG attacked, his group resisted until the very end!",
    (2,13,80): "Impressive! He looks tough.",
    (2,13,81): "You're not bad yourselves! You drove off that ROG punk Pukumon. We'll protect this place from now on. Come to us if you need anything!",
    (2,13,82): "All right, let's hurry to the next tower!",
    (2,13,83): "Ready to return to the Xros Loader?",
    (2,13,84): "Give me a second. I'll open it.",
    (2,13,85): "Restoring this tower should bring back more Digimon, right? I can't wait!",
    (2,13,86): "Sky Fort's systems came back online!",
    (2,13,87): "A new Farm Island was created!",
    (2,13,88): "Please give this Farm Island a good name.",
    (2,13,89): "Yeah, that sounds good! We also regained access to another Data Library folder.",
    (2,13,90): "Obtained a DigiScore!\n~I",
    (2,13,91): "Obtained a DigiScore!\n~I",
    (2,13,92): "Obtained a DigiScore!\n~I",
    (2,13,93): "Obtained a DigiScore!\n~I",
    (2,13,94): "That's another tower restored! We gained a new Farm Island and more DigiScores too!",
    (2,13,95): "Every Capacitor Tower we restore brings more of Sky Fort's systems back online.",
    (2,13,96): "And more Digimon may have returned. Let's go see who's here!",
    (2,13,97): "Kuwagamon? Did he live around here?",
    (2,13,98): "I came from far away, drifting wherever the road took me. After wandering into this place, I grew attached to it. If you'll have me, I'll settle down and give this home everything I've got.",
    (2,13,99): "Is this guy okay? He's awfully laid-back...",
    (2,13,100): "Of course! Kuwagamon's pincers are incredibly strong. The kids love him too!",
    (2,13,101): "Well, stag beetles are pretty cool.",
    (2,13,102): "All this praise is getting me fired up! I'm looking forward to helping out!",
    (2,13,103): "Great! Now let's hurry to the next tower!",
    (2,13,104): "Ready to return to the Xros Loader, Taiki?",
    (2,13,105): "All right. Let's open this door!",
    (2,13,106): "Every Capacitor Tower looks the same. It almost feels like we keep returning to the same place.",
    (2,13,107): "Sky Fort's systems came back online!",
    (2,13,108): "A new Farm Island was created!",
    (2,13,109): "Please name the new Farm Island.",
    (2,13,110): "Hmm... Seventy-two points! No, wait... Ninety-eight! Yeah, that's more like it! Oh, another Data Library folder is accessible!",
    (2,13,111): "Obtained a DigiScore!\n~I",
    (2,13,112): "Obtained a DigiScore!\n~I",
    (2,13,113): "Obtained a DigiScore!\n~I",
    (2,13,114): "Obtained a DigiScore!\n~I",
    (2,13,115): "Spadamon, I still don't understand which Farm Goods I should place on an island. What should I choose?",
    (2,13,116): "Some Farm Goods raise stats like Strength or Speed, while others increase the EXP Digimon earn. Choose whatever best supports the Digimon you're raising!",
    (2,13,117): "I see. They're kind of expensive, though. I wish they were easier to get.",
    (2,13,118): "B-but good equipment costs money! Strong enemies could appear anytime. We can't pinch pennies when our Digimon need quality Farm Goods!",
    (2,13,119): "Don't worry. Taiki will figure it out. More importantly, let's see who came back!",
    (2,13,120): "Mammon! And Zudomon too!",
    (2,13,121): "You finally reclaimed the tower from ROG! Thank you, Spadamon!",
    (2,13,122): "You worked hard to restore it. We'll guard this Capacitor Tower from now on.",
    (2,13,123): "Thank you!",
    (2,13,124): "We can leave this place to them. Shall we move on?",
    (2,13,125): "Ready to return to the Xros Loader?",
    (2,13,126): "Oh, right! Then we're counting on you, Taiki!",
    (2,13,127): "I'll open it. Just give me a moment.",
    (2,13,128): "Taiki, start thinking of a name for the next Farm Island!",
    (2,13,129): "Sky Fort's systems came back online!",
    (2,13,130): "A new Farm Island was created!",
    (2,13,131): "All right, Taiki. Please name the new Farm Island.",
    (2,13,132): "Yeah, nice! It's simple and easy to remember. Another Data Library folder is accessible too!",
    (2,13,133): "Obtained a DigiScore!\n~I",
    (2,13,134): "Obtained a DigiScore!\n~I",
    (2,13,135): "Obtained a DigiScore!\n~I",
    (2,13,136): "Obtained a DigiScore!\n~I",
    (2,13,137): "Obtained a DigiScore!\n~I",
    (2,13,138): "Come to think of it, I've wanted to ask you something, Taiki. Why did you and the others come to the El Est Zone?",
    (2,13,139): "Why? Because you called us, Spadamon. Taiki heard your voice.",
    (2,13,140): "We were in the jungle, standing before the lost Weapon Digimon, when a strange light swallowed us and threw us into this Zone. We assumed you summoned us.",
    (2,13,141): "What? I called Taiki? I don't remember doing anything like that!",
})

# Batch 2Z: global prose records 2742-3059 (2,001 draft-English words).
OVERRIDES.update({
    (2,13,142): "Really? Then who called us to this Zone? Well, we can solve that mystery later. Let's head into town.",
    (2,13,143): "Devitamamon! And Puppetmon too!",
    (2,13,144): "We heard the rumors and rushed back, Pino! Spadamon and Xros Heart, it's great to see you, Pino!",
    (2,13,145): "I'm tired of running away. With all of us together, I think we can change this Zone!",
    (2,13,146): "Leave it to us! From now on, let's enjoy our home!",
    (2,13,147): "You have a lot of good friends, Spadamon.",
    (2,13,148): "Yeah. Everyone could come home because of Taiki and the others. Thank you!",
    (2,13,149): "You're welcome! At this rate, we'll restore everything in no time!",
    (2,13,150): "I'll open the door now. Give me a moment.",
    (2,13,151): "Taiki, start thinking about the theme for our next Farm Island!",
    (2,13,152): "Sky Fort's systems came back online!",
    (2,13,153): "A new Farm Island was created!",
    (2,13,154): "Please name the new Farm Island.",
    (2,13,155): "Thanks, Taiki! That's a great name. Just what I'd expect from you! We also regained access to another Data Library folder.",
    (2,13,156): "Obtained a DigiScore!\n~I",
    (2,13,157): "Obtained a DigiScore!\n~I",
    (2,13,158): "Obtained a DigiScore!\n~I",
    (2,13,159): "Obtained a DigiScore!\n~I",
    (2,13,160): "Obtained a DigiScore!\n~I",
    (2,13,161): "Obtained a DigiScore!\n~I",
    (2,13,162): "Hey, do you two like sweets?",
    (2,13,163): "Why the sudden question, Spadamon?",
    (2,13,164): "Once we've freed the Zone from ROG, let's celebrate Sky Fort's return with a huge cake!",
    (2,13,165): "Great idea! We could have fireworks too. From Sky Fort, every Zone would be able to see them!",
    (2,13,166): "Fireworks? That sounds delicious!",
    (2,13,167): "They're not food...",
    (2,13,168): "I hear someone outside! Let's go!",
    (2,13,169): "Cannondramon!",
    (2,13,170): "Sorry we left everything to you. From now on, we'll do our part too!",
    (2,13,171): "We're counting on you. Thanks!",
    (2,13,172): "We'll always be here. Come see us whenever you need help.",
    (2,13,173): "Everyone here is so kind.",
    (2,13,174): "Yeah. They really are.",
    (2,13,175): "All right, on to the next one! Let's keep moving!",
    (2,13,176): "Please wait a moment.",
    (2,13,177): "Huh? That's strange. My power still hasn't returned. Maybe we have to defeat ROG's leader first...",
    (2,13,178): "Yes, recruit this Digimon.",
    (2,13,179): "No, not yet.",
    (2,13,180): "You cannot recruit this Digimon. Please release one first.",
    (2,13,181): "I want to live here...",
    (2,13,182): "Will you let me join you?",
    (2,13,183): "Can I join your team?",
    (2,13,184): "Will you take me with you?",
    (2,13,185): "Would you let me join you?",
    (2,13,186): "Will you recruit me?",
    (2,13,187): "You're really letting me join?",
    (2,13,188): "Can I come with you?",
    (2,13,189): "Talk to me whenever you're ready.",
    (2,13,190): "If you're fighting those villains, let me join you!",
    (2,13,191): "I'm always ready to fight.",
    (2,13,192): "Quit hesitating and recruit me already.",
    (2,13,193): "Recruit me.",
    (2,13,194): "Let me join you!",
    (2,13,195): "If you need help, recruit me.",
    (2,13,196): "Dorulumon joined you!",
    (2,13,197): "Sparrowmon joined you!",
    (2,13,198): "Beelzemon joined you!",
    (2,13,199): "SkullKnightmon joined you!",
    (2,14,0): "DeadlyAxemon joined you!",
    (2,14,1): "Greymon joined you!",
    (2,14,2): "MailBirdramon joined you!",
    (2,14,3): "All right. Thanks.",
    (2,14,4): "Let's do our best!",
    (2,14,5): "Understood. I'm counting on you.",
    (2,14,6): "I'll show you my power!",
    (2,14,7): "Got it.",
    (2,14,8): "I'll crush everything in our way!",
    (2,14,9): "Let's put this power to work.",
    (2,14,10): "Dorulumon was added to the party!",
    (2,14,11): "Sparrowmon was added to the party!",
    (2,14,12): "Beelzemon was added to the party!",
    (2,14,13): "SkullKnightmon was added to the party!",
    (2,14,14): "DeadlyAxemon was added to the party!",
    (2,14,15): "Greymon was added to the party!",
    (2,14,16): "MailBirdramon was added to the party!",
    (2,14,17): "Dorulumon was sent to the DigiBank.",
    (2,14,18): "Sparrowmon was sent to the DigiBank.",
    (2,14,19): "Beelzemon was sent to the DigiBank.",
    (2,14,20): "SkullKnightmon was sent to the DigiBank.",
    (2,14,21): "DeadlyAxemon was sent to the DigiBank.",
    (2,14,22): "Greymon was sent to the DigiBank.",
    (2,14,23): "MailBirdramon was sent to the DigiBank.",
    (2,14,24): "Hmm. I understand.",
    (2,14,25): "I see.",
    (2,14,26): "Okay, got it.",
    (2,14,27): "What a fool.",
    (2,14,28): "Understood.",
    (2,14,29): "You won't recruit me?",
    (2,14,30): "Hmph.",
    (2,14,31): "^0 joined you!",
    (2,14,32): "^0 was added to the party!",
    (2,14,33): "^0 joined you!",
    (2,14,34): "^0 was sent to the DigiBank.",
})

# Generic recruitment prompts and responses retain small voice variations while
# using consistent English terminology.
_RECRUIT_QUESTIONS = (
    "Will you recruit me?", "Can I join your team?", "Will you take me with you?",
    "Could we be friends?", "May I come along?", "Will you let me join you?",
)
for _index in range(35, 65):
    OVERRIDES[(2, 14, _index)] = _RECRUIT_QUESTIONS[(_index - 35) % len(_RECRUIT_QUESTIONS)]
_RECRUIT_ACCEPT = (
    "Thanks! I'm counting on you!", "Nice to meet you!", "Let's do our best!",
    "Glad to be on the team!", "Thanks for having me!", "I won't let you down!",
)
for _index in range(65, 93):
    OVERRIDES[(2, 14, _index)] = _RECRUIT_ACCEPT[(_index - 65) % len(_RECRUIT_ACCEPT)]
_RECRUIT_DECLINE = (
    "Oh, I see.", "That's disappointing...", "Maybe next time.", "Okay. See you around.",
    "I understand.", "No problem. Come back anytime.",
)
for _index in range(93, 122):
    OVERRIDES[(2, 14, _index)] = _RECRUIT_DECLINE[(_index - 93) % len(_RECRUIT_DECLINE)]

OVERRIDES.update({
    (2,14,122): "Check the Quest Monitor?",
    (2,14,123): "Yes, check it.",
    (2,14,124): "No, not now.",
    (2,14,125): "Use the DigiLab?",
    (2,14,126): "Yes, use it.",
    (2,14,127): "No, not now.",
    (2,14,128): "Use the DigiFarm?",
    (2,14,129): "Yes, use it.",
    (2,14,130): "No, not now.",
    (2,14,131): "Maybe adding green beans will work... No, it still isn't moving. The switch is on. Is it not receiving any power?",
    (2,14,132): "It doesn't need food... Maybe it just doesn't have enough energy?",
    (2,14,133): "Hey, Taiki! How long are you going to sleep?",
    (2,14,134): "Huh? Shoutmon? What's wrong?",
    (2,14,135): "What's wrong?! Get a hold of yourself!",
    (2,14,136): "Hey, Taiki! How long are you going to sleep?",
    (2,14,137): "Huh? Shoutmon? What's wrong?",
    (2,14,138): "What's wrong?! Get a hold of yourself!",
    (2,14,139): "Taiki, are you okay? Don't push yourself too hard.",
    (2,14,140): "Right! Don't overdo it, but don't hold back either. Fight hard and win! You can do it, Taiki!",
    (2,14,141): "Yeah. Leave it to me!",
    (2,14,142): "Are you okay, Taiki?",
    (2,14,143): "You were tossing and turning. Did you have a nightmare?",
    (2,14,144): "Sorry, everyone. I'm okay now!",
    (2,14,145): "Be careful! Don't overdo it!",
    (2,14,146): "If you don't understand something, ask us or Patamon, Taiki Kudo!",
    (2,14,147): "Stay strong, Taiki!",
    (2,14,148): "Show us what you've got, General! Give it everything!",
    (2,14,149): "I'm fine now! We can't give up!",
    (2,14,150): "Taiki, this is the Service Counter. Use tickets earned from Reload Challenges to summon Digimon.",
    (2,14,151): "Yes, use a ticket.",
    (2,14,152): "No, not now.",
    (2,14,153): "Bring me another ticket whenever you want to summon a Digimon!",
})

_ITEM_GIVE = (
    "Here, take this item!", "You earned this. Here you go!", "I'll give you this item.",
    "Go on, take it!", "This item is yours.", "Fine. You can have this item.",
)
for _index in range(154, 200):
    OVERRIDES[(2, 14, _index)] = _ITEM_GIVE[(_index - 154) % len(_ITEM_GIVE)]
for _index in range(0, 25):
    OVERRIDES[(2, 15, _index)] = _ITEM_GIVE[(_index + 2) % len(_ITEM_GIVE)]
_ITEM_FAREWELL = (
    "Take good care of it. See you!", "Use it well!", "Hope it helps. See you around!",
    "Don't waste it!", "Make the most of it!", "Take care now!",
)
for _index in range(25, 60):
    OVERRIDES[(2, 15, _index)] = _ITEM_FAREWELL[(_index - 25) % len(_ITEM_FAREWELL)]

# Batch 3A: global prose records 3060-3196 (2,008 draft-English words).
for _index in range(60, 96):
    OVERRIDES[(2, 15, _index)] = _ITEM_FAREWELL[(_index - 60) % len(_ITEM_FAREWELL)]
OVERRIDES.update({
    (2,15,96): "Taiki, big news! That portal now connects to the DigiColosseum!",
    (2,15,97): "What's the DigiColosseum?",
    (2,15,98): "It's a battle arena in the Colosseum Zone! Its portals supposedly appeared only in peaceful Zones, but now we're connected too!",
    (2,15,99): "That's amazing! What happens there?",
    (2,15,100): "You battle heroes from across the Digital World! Win to raise your rank and earn prizes. Come on, let's check it out!",
    (2,15,101): "Welcome to the DigiColosseum!",
    (2,15,102): "So this is the DigiColosseum...",
    (2,15,103): "That's right! Records say this magnificent arena has existed beyond ordinary time since the Digital World's earliest days. This is the legendary DigiColosseum!",
    (2,15,104): "Wow. I had no idea...",
    (2,15,105): "Some even say the DigiColosseum is as old as the Digital World itself. Only chosen Digimon may enter!",
    (2,15,106): "Wait! I'm not a Digimon, as you can clearly see...",
    (2,15,107): "You guide Digimon in battle, correct? Leader, Tamer, Breeder, General—whatever the title, people like you are welcome too!",
    (2,15,108): "Good to know. What are my Digimon and I supposed to do here?",
    (2,15,109): "This is a stage where accomplished teams from across the Digital World test their strength against one another.",
    (2,15,110): "First, speak to Minomon at the counter. He'll enter you in the tournament matching your rank.",
    (2,15,111): "Is there an entry fee? I don't have much money...",
    (2,15,112): "You need only the strength and skill you've developed, plus the courage and friendship shared with your partners. No money or special items are required.",
    (2,15,113): "I see...",
    (2,15,114): "After entering, speak to Knightmon. He'll open the portal to the Battle Stage, where you'll face that rank's Battle Master. Win and your Master Rank will rise.",
    (2,15,115): "Reach the highest rank, Legend Master, and you'll become a new legend yourself! Whoa! That's so cool!",
    (2,15,116): "Enter a tournament and you'll understand. Just climb one step at a time.",
    (2,15,117): "All right, I'll try it! Thanks for explaining!",
    (2,15,118): "Welcome! This is the entry counter for the DWM Tournament, where Digimon prove their true strength!",
    (2,15,119): "DWM?",
    (2,15,120): "It means Digital World Master. There are five ranks: Bronze, Silver, Gold, Platinum, and Legend. Defeat a rank's Battle Master to earn that title. Understand?",
    (2,15,121): "Talk to me whenever you'd like to enter. I'll be waiting!",
    (2,15,122): "You're already a Legend Master! That's DWM's highest title. You're one incredible Master!",
    (2,15,123): "The Digital World's future is in your hands! Woo-hoo!",
    (2,15,124): "You're currently entered in a tournament. Cancel your entry?",
    (2,15,125): "Yes, cancel it.",
    (2,15,126): "No, stay entered.",
    (2,15,127): "Understood. Your entry has been canceled.",
    (2,15,128): "Enter again whenever you're ready. I'll be waiting!",
    (2,15,129): "Speak to Knightmon on the lower right. He'll open the portal to the Battle Stage.",
    (2,15,130): "Good luck!",
    (2,15,131): "Enter the Bronze Master Tournament?",
    (2,15,132): "You're entered! Speak to Knightmon on the lower right, then use the portal to reach the Battle Stage.",
    (2,15,133): "Enter the Silver Master Tournament?",
    (2,15,134): "Enter the Gold Master Tournament?",
    (2,15,135): "Enter the Platinum Master Tournament?",
    (2,15,136): "Enter the Legend Master Tournament? Amazing! I'm getting excited!",
    (2,15,137): "Well done, Taiki Kudo!",
    (2,15,138): "How do you know my name?",
    (2,15,139): "This is the DigiColosseum, heart of the Digital World! Anyone strong enough to reach us is thoroughly documented—name, face, partners, hobbies, habits, even sleeping style!",
    (2,15,140): "Knowing that much is a little creepy... Anyway, what do you do here?",
    (2,15,141): "This is the Winners' Reward Counter! Talk to me after each tournament victory and I'll give you a special item worthy of a young hero protecting the Digital World's future!",
    (2,15,142): "You're seriously creeping me out! Let's go, Taiki Kudo!",
    (2,15,143): "Hurry and become a Bronze Master, Taiki Kudo! Your special reward is ready!",
    (2,15,144): "You became a Bronze Master! Congratulations! Here's your special reward!",
    (2,15,145): "Obtained LH Slasher!",
    (2,15,146): "Obtained Tiferet!",
    (2,15,147): "How does Bronze Master feel? Next comes Silver Master. Keep going, Taiki Kudo!",
    (2,15,148): "Hurry and become a Silver Master, Taiki Kudo! A special reward is waiting!",
    (2,15,149): "You became a Silver Master! Congratulations! Here's your special reward!",
    (2,15,150): "Obtained Sodom & Gomorrah!",
    (2,15,151): "Obtained Purge Shine!",
    (2,15,152): "Silver is only another step. Gold Master is next! Go, Taiki Kudo!",
    (2,15,153): "Hurry and become a Gold Master, Taiki Kudo! Your reward is ready!",
    (2,15,154): "You became a Gold Master! Impressive! Here's your special reward!",
    (2,15,155): "Obtained Claíomh Solais!",
    (2,15,156): "Obtained Scale Mail!",
    (2,15,157): "Gold was only the warm-up. Platinum is where it gets serious! Show us your strength, Taiki Kudo!",
    (2,15,158): "Hurry and become a Platinum Master, Taiki Kudo! A special reward awaits!",
    (2,15,159): "You became a Platinum Master! Congratulations! Here's your special reward!",
    (2,15,160): "Obtained Royal M Star!",
    (2,15,161): "Obtained Niflheim!",
    (2,15,162): "You've raced up to Platinum, but Legend Master is the true goal. Win once more and you'll be Taiki the Legend Master!",
    (2,15,163): "Become a Legend Master, Taiki Kudo! Everyone's watching, and this reward is truly special—almost as if it was made for you.",
    (2,15,164): "You did it! You're finally a Legend Master! Congratulations! Accept this extraordinary reward—you've earned it!",
    (2,15,165): "Obtained Gorgon!",
    (2,15,166): "Obtained the Legend Medal!",
    (2,15,167): "Use it well, Taiki the Legend Master!",
    (2,15,168): "Taiki the Legend Master, no higher rank remains. Now you're the one everyone aspires to surpass. I have no rewards left, but the Digital World's bright future will be your ultimate prize.",
    (2,15,169): "Many challenges still await. Keep it up, Taiki the Legend Master!",
    (2,15,170): "Enter a tournament before visiting the Battle Stage. Minomon handles DWM Tournament registration.",
    (2,15,171): "You're entered in the DWM Tournament.",
    (2,15,172): "Are you ready?",
    (2,15,173): "Enter the Battle Stage?",
    (2,15,174): "Let's go!",
    (2,15,175): "Not yet.",
    (2,15,176): "Talk to me again when you're ready.",
    (2,15,177): "If you're ready to leave, proceed ahead.",
    (2,15,178): "That portal leads to the Battle Stage. Go show them what you've got!",
    (2,15,179): "This portal is for Battle Masters. Challengers use the portal opposite this one.",
    (2,15,180): "Welcome!",
    (2,15,181): "Come again!",
    (2,15,182): "Now entering the DWM Bronze Master Tournament: Team Xros Heart, led by General Taiki Kudo!",
    (2,15,183): "Their opponent is the Bronze Battle Master, a familiar face from Digimon Story! The eccentric scientist who keeps bringing children into the Digital World—leader of Team Chrono!",
    (2,15,184): "Mr. Kogure!",
    (2,15,185): "That introduction makes me sound like a villain...",
    (2,15,186): "Before we begin, Battle Master Kogure has a few words for the challenger!",
    (2,15,187): "I've fought countless unforgettable battles here since the DigiColosseum opened. Taiki, I sense this will be another great one. Let neither of us hold back!",
    (2,15,188): "Right! I'll give it everything!",
    (2,15,189): "Team Chrono, led by Battle Master Kogure, versus Team Xros Heart, led by General Taiki! The showdown begins now!",
    (2,15,190): "May both teams give their all in a fair and thrilling battle!",
    (2,15,191): "Ready... Fight!",
    (2,15,192): "The winner is Team Xros Heart! General Taiki has defeated Battle Master Kogure and Team Chrono! Congratulations!",
    (2,15,193): "Congratulations, General Taiki and Team Xros Heart! You are now Bronze Masters. Remember: what matters isn't the rank itself, but how you live up to it.",
    (2,15,194): "I'll work hard to remain worthy of this rank.",
    (2,15,195): "Good. I expected no less from you, General Taiki!",
    (2,15,196): "Team Xros Heart and General Taiki appeared without warning in the Digital World! What battles await them next? Follow their future—and join us next time!",
})

# Batch 3B: global prose records 3197-3287 (2,007 draft-English words).
OVERRIDES.update({
    (2,15,197): "Now for the DWM Silver Master Tournament! First, our challenger: Team Xros Heart, led by General Taiki Kudo!",
    (2,15,198): "Their Battle Master is this fiery young hero—the shining champion of Sunshine City!",
    (2,15,199): "Battle Master Koh and Team Sunburst!",
    (2,16,0): "So you're my next challenger, General Taiki! Can you handle my burning spirit?!",
    (2,16,1): "Sparks are already flying! Before champion and challenger collide, Battle Master Koh has a few words!",
    (2,16,2): "I have nothing to say to a challenger—because I'm always a challenger too! Why don't you say something to me instead?",
    (2,16,3): "How am I supposed to answer that? Was he always like this? I heard he used to be quiet...",
    (2,16,4): "Team Sunburst, led by Battle Master Koh, versus Team Xros Heart, led by General Taiki! This clash of heroes will ignite the DigiColosseum!",
    (2,16,5): "May both teams give their all in a fair and thrilling battle!",
    (2,16,6): "Ready... Fight!",
    (2,16,7): "A flawless victory for Team Xros Heart! General Taiki clears the first Silver Master match! Battle Master Koh, what did you think?",
    (2,16,8): "You're every bit as strong as the rumors, General Taiki! I may have lost, but my challenger's spirit still burns! Only my carefully hidden glass pride was shattered!",
    (2,16,9): "Is this seriously his personality? He's nothing like what I heard!",
    (2,16,10): "Something intense is passing between them! Battle Master Koh changes Team Sunburst's formation to meet the challenger. The second match begins!",
    (2,16,11): "May both teams give their all in a fair and thrilling battle!",
    (2,16,12): "Ready... Fight!",
    (2,16,13): "General Taiki and Team Xros Heart win again! They have defeated Battle Master Koh and Team Sunburst to become Silver Masters! Congratulations!",
    (2,16,14): "Congratulations, General Taiki and Team Xros Heart! You're Silver Masters now. Your passionate, powerful fighting style burned as brightly as Sunburst!",
    (2,16,15): "Thank you, Battle Master. That means a lot.",
    (2,16,16): "Passion alone won't win every battle. Stay focused and keep pushing forward. Good luck, Xros Heart!",
    (2,16,17): "The sensational newcomers, Team Xros Heart and General Taiki, have taken the DigiColosseum by storm! What battle awaits them next? Join us next time!",
    (2,16,18): "Now for the DWM Gold Master Tournament! Our challenger is Team Xros Heart, led by General Taiki Kudo!",
    (2,16,19): "Their Gold Battle Master needs no introduction. You saw her at the Silver Tournament—the cool beauty of Darkmoon City!",
    (2,16,20): "Battle Master Sayo and Team Moonlight!",
    (2,16,21): "Welcome, rising star. Now I'll see your strength for myself.",
    (2,16,22): "What composure before battle! Her fighting spirit burns quietly within. Battle Master Sayo, a few words for the challenger!",
    (2,16,23): "You're General Taiki. I've heard about you and the new-generation technique you call DigiXros.",
    (2,16,24): "I've heard about you too, Battle Master Sayo—the calmest Master in the DigiColosseum.",
    (2,16,25): "Team Moonlight, led by Battle Master Sayo, versus Team Xros Heart, led by General Taiki! Two opposing powers collide in a battle unlike Sunburst!",
    (2,16,26): "May both teams give their all in a fair and thrilling battle!",
    (2,16,27): "Ready... Fight!",
    (2,16,28): "Team Xros Heart wins! General Taiki claims the first of three victories needed for Gold Master! Battle Master Sayo, your thoughts?",
    (2,16,29): "You possess remarkable strength and vitality. I'll admit that much. But endurance comes from experience, and I'll show you the difference between our careers.",
    (2,16,30): "I know you have more experience. Even so, I'll show you the power of Xros Heart!",
    (2,16,31): "Both sides quietly prepare! Battle Master Sayo adjusts Team Moonlight's formation. The second match against Xros Heart begins!",
    (2,16,32): "May both teams give their all in a fair and thrilling battle!",
    (2,16,33): "Ready... Fight!",
    (2,16,34): "Team Xros Heart wins again! That's two of the three victories General Taiki needs. Only one remains! Battle Master Sayo seems unfazed...",
    (2,16,35): "I expected this. Anyone capable of becoming Silver Master could also reach Gold. That much was obvious.",
    (2,16,36): "Seriously?! She's even sharper than she was during the Silver Tournament...",
    (2,16,37): "Battle Master Sayo changes Team Moonlight's formation again. Can General Taiki and Team Xros Heart finish it in the next battle?",
    (2,16,38): "May both teams give their all in a fair and thrilling battle!",
    (2,16,39): "Ready... Fight!",
    (2,16,40): "They've done it! Team Xros Heart wins! General Taiki has defeated Battle Master Sayo and Team Moonlight to become Gold Master! Congratulations!",
    (2,16,41): "General Taiki, you're now a Gold Master—one of the Digital World's elite. Greater and stranger challenges await, so prepare yourself.",
    (2,16,42): "Understood. I'll stay focused and keep doing my best.",
    (2,16,43): "You'll be fine. I have no doubts.",
    (2,16,44): "Team Xros Heart has defeated two mighty teams in succession: Sunburst and Moonlight! How long can General Taiki's streak continue? Join us next time!",
    (2,16,45): "It's time for the DWM Platinum Master Tournament! The challenger is Team Xros Heart, led by General Taiki!",
    (2,16,46): "And the Battle Master they'll face is... quite a character!",
    (2,16,47): "A super digital life-form created by Yggdrasil: Captain Uno! He leads the team once feared across the Digital World—the Bandits!",
    (2,16,48): "The mood suddenly got awfully strange... Please remember this is the DigiColosseum. And this time our opponent looks unbelievably lazy. What's with that attitude?",
    (2,16,49): "It seems the announcer's inner voice is leaking out! Before the battle, Captain Uno has a few words for the challenger!",
    (2,16,50): "Sit down! I'll blow you away!",
    (2,16,51): "What?!",
    (2,16,52): "The Bandits have come a long way, and Captain Uno is raring to go! How far can Xros Heart push them? This will test General Taiki's leadership!",
    (2,16,53): "May both teams give their all in a fair and thrilling battle!",
    (2,16,54): "Ready... Fight!",
    (2,16,55): "Team Xros Heart wins! General Taiki clears the first Platinum Master match! Captain Uno does not look convinced!",
    (2,16,56): "Of course I'm not convinced! If I accepted that loss, it'd count as a loss! Wait... I guess it counts either way!",
    (2,16,57): "I have no idea what you're talking about...",
    (2,16,58): "General Taiki stares in disbelief! What will happen in the second match between Team Bandits and Team Xros Heart?",
    (2,16,59): "Uno, what did you break this time? I was in the middle of maintaining the DigiShip...",
    (2,16,60): "Wait, this is the DigiColosseum?! Uno, what are you doing here?!",
    (2,16,61): "A new arrival! It's Professor Dos, Team Bandits' brilliant engineer! Can he get Captain Uno back into fighting shape?",
    (2,16,62): "He challenged this kid and got flattened. Uno hasn't changed at all. Honestly, you need to grow up!",
    (2,16,63): "Hold on! You're making it sound like I'm always creating messes for you!",
    (2,16,64): "Because you are! Fine, step aside and watch. I'm better at handling this kid than you are!",
    (2,16,65): "Preparations are complete! Captain Uno and Professor Dos lead Team Bandits against General Taiki and Team Xros Heart! The second match begins!",
    (2,16,66): "May both teams give their all in a fair and thrilling battle!",
    (2,16,67): "Ready... Fight!",
    (2,16,68): "General Taiki and Team Xros Heart win the second Platinum match! Professor Dos, what did you think of the challenger?",
    (2,16,69): "I'm an adult, and they're children. Of course I couldn't fight them seriously!",
    (2,16,70): "That's a rather childish excuse...",
    (2,16,71): "Both sides glare fiercely at one another! Captain Uno, what did you think of that battle?",
    (2,16,72): "They're not nearly as tough as Dos claims! Though they did fight pretty well...",
    (2,16,73): "Wait! Why is Three here?!",
    (2,16,74): "The true star finally arrives! Team Bandits' beautiful leader cloaked in shadow—Princess Three!",
    (2,16,75): "What are you two doing here? And you removed that idiot Kernel from the archive! He'll sing all night while everyone sleeps. Even if you reboot him, he'll just return!",
    (2,16,76): "We didn't come here by choice! And Dos was the one who forgot to put Kernel away!",
    (2,16,77): "I didn't forget. I was dragged here before I could! Then, before I understood anything, Uno forced me to fight this kid.",
    (2,16,78): "Stop calling them children just because they're young. And don't embarrass yourselves by making excuses.",
    (2,16,79): "You're calling us kids? You're young too! Besides, you probably couldn't do any better!",
    (2,16,80): "Is Team Bandits falling apart? Their battle with Xros Heart continues despite the accusations flying everywhere. The third match begins!",
    (2,16,81): "May both teams give their all in a fair and thrilling battle!",
    (2,16,82): "Ready... Fight!",
    (2,16,83): "Team Xros Heart wins again! General Taiki clears the third match and needs only one more victory for Platinum Master! Team Bandits is in serious trouble!",
    (2,16,84): "Uno, Three... What do we do? This is getting dangerous!",
    (2,16,85): "Why are you two panicking? What a pain. Maybe we should just slip away while nobody's looking.",
    (2,16,86): "We can't run now! If we have to fight, then let's show them EX Eraser's overwhelming power!",
    (2,16,87): "What are you saying? Raw power is meaningless. EX Eraser's true strength is its blinding speed!",
})

# Batch 3C: global prose records 3288-3376 (2,016 draft-English words).
OVERRIDES.update({
    (2,16,88): "Then we won't settle anything by arguing. EX Eraser will prove whether power or speed matters more!",
    (2,16,89): "To be clear, it's obviously speed.",
    (2,16,90): "Then we'll settle it in battle!",
    (2,16,91): "What kind of logic is that? Even Kernel would know better.",
    (2,16,92): "Leave Kernel out of this! We'll handle it ourselves!",
    (2,16,93): "Fine! Then let's go all out!",
    (2,16,94): "We'll show you the Bandits' true strength! This won't be easy!",
    (2,16,95): "It's the legendary EX Eraser! The Bandits' secret combination technique, seen only once before at the DigiColosseum! I never thought we'd witness it again!",
    (2,16,96): "No more excuses! If you're scared, surrender now!",
    (2,16,97): "After seeing that, we can't hold back. Their combination is incredible, but now Xros Heart has to show them what a real fusion can do!",
    (2,16,98): "There he goes again. Is everyone in the Digital World this loud? Three, help me out here!",
    (2,16,99): "Sparks fly around EX Eraser! Team Bandits and Team Xros Heart begin the decisive fourth match!",
    (2,16,100): "May both teams give their all in a fair and thrilling battle!",
    (2,16,101): "Ready... Fight!",
    (2,16,102): "General Taiki and Team Xros Heart win the fourth match and become Platinum Masters! Even EX Eraser could not save Team Bandits! Congratulations!",
    (2,16,103): "Since we lost, I have to accept it. Still, I never imagined a kid like you would become Platinum Master.",
    (2,16,104): "Don't mock him, Uno. A loss is a loss. Congratulations, General Taiki. You are unquestionably a Platinum Master.",
    (2,16,105): "The Bandits are always this ridiculous. Don't expect some grand speech like, 'Go forth over our fallen bodies, young hero.'",
    (2,16,106): "Thank you, Bandits. Becoming Platinum Master is great, but earning recognition from DigiColosseum veterans means even more.",
    (2,16,107): "Hmph. If you're going to say it like that, I guess I have to acknowledge you—even if your nice-guy act is boring!",
    (2,16,108): "The Bandits have praised their challenger—a rare sight indeed! General Taiki and Team Xros Heart have reached Platinum Master. Next awaits the legendary final rank! Join us next time!",
    (2,16,109): "Now for the DWM Legend Master Tournament! The challenger is Team Xros Heart, led by General Taiki Kudo!",
    (2,16,110): "And in the champion's corner stands our Battle Master! But who could it be? Legend tournaments are so rare that even the champion's identity is a mystery!",
    (2,16,111): "What?! The mighty Battle Master is... Koromon!",
    (2,16,112): "Battle Master Koromon gives a tiny hop! Behind that cute appearance are abilities that defy all expectations. He's warming up before the challenger!",
    (2,16,113): "K-Koromon?! How can such a tiny Digimon be the Battle Master?",
    (2,16,114): "Another hop from Battle Master Koromon! Is he showing off, intimidating his opponent, or simply being adorable? The crowd is going wild!",
    (2,16,115): "But what team does the Battle Master command?",
    (2,16,116): "This is huge! The Battle Master's team is Immortal Brave!",
    (2,16,117): "For those unfamiliar: Immortal Brave is an all-star team. Its members are chosen from the data, dreams, and bonds of heroes and rivals across the Digital World—brilliant souls connected by the heart!",
    (2,16,118): "Or ImmoBrave for short!",
    (2,16,119): "What?! Why did Battle Master Koromon suddenly glare at me? Doesn't he like my nickname?",
    (2,16,120): "A-all right! Without further delay, let's welcome Immortal Brave!",
    (2,16,121): "Koromon... I've heard that name before. Wasn't there a Koromon who met a human long ago, then suddenly grew enormous? Could this be him?",
    (2,16,122): "The Digital World's legends are alive and well! Perhaps the challenger's tale will become another shining chapter of Immortal Brave!",
    (2,16,123): "Battle Master Koromon and Team Immortal Brave face General Taiki and Team Xros Heart! This historic confrontation cannot be missed!",
    (2,16,124): "It hardly needs saying now, but may both teams give their all in a fair battle!",
    (2,16,125): "Ready... Fight!",
    (2,16,126): "The winner of the first Legend Master match is Team Xros Heart! General Taiki! Battle Master Koromon, what did you think?",
    (2,16,127): "Koromon appears to praise the challenger's effort. Immortal Brave changes members and adopts a new formation. The heated second match begins!",
    (2,16,128): "May both teams give their all in a fair and thrilling battle!",
    (2,16,129): "Ready... Fight!",
    (2,16,130): "The winner of the second Legend Master match is Team Xros Heart! General Taiki wins again! Battle Master Koromon remains composed.",
    (2,16,131): "That's Battle Master Koromon for you. He may look small, but he's a living legend.",
    (2,16,132): "The fierce battle continues—in fact, it's only beginning! Immortal Brave and Xros Heart start the third Legend Master match!",
    (2,16,133): "May both teams give their all in a fair and thrilling battle!",
    (2,16,134): "Ready... Fight!",
    (2,16,135): "Unbelievable! Team Xros Heart wins the third Legend Master match! General Taiki has taken three straight victories against a living legend!",
    (2,16,136): "What's this? Battle Master Koromon looks genuinely upset! The next match could be fierce! General Taiki, your response?",
    (2,16,137): "However he comes at us, we'll be ready.",
    (2,16,138): "What confidence! Battle Master Koromon is even more fired up. A Digimon hurricane may be coming!",
    (2,16,139): "Before that hurricane blows away the DigiColosseum, let's continue! Immortal Brave versus Xros Heart—the turbulent fourth match begins!",
    (2,16,140): "May both teams give their all in a fair and thrilling battle!",
    (2,16,141): "Ready... Fight!",
    (2,16,142): "Who could have predicted this? General Taiki and Team Xros Heart win the fourth Legend Master match! Living Legend Koromon is cornered!",
    (2,16,143): "General Taiki, only one victory separates you from Legend Master! Tell us how you feel!",
    (2,16,144): "Don't say that yet! What if it makes Koromon even angrier?",
    (2,16,145): "Battle Master Koromon is furious—at the challenger, or perhaps at my commentary! He somehow looks far more intimidating than usual!",
    (2,16,146): "At last, the fifth Legend Master match! A battle never before completed in this colosseum is about to reach its conclusion!",
    (2,16,147): "May both teams give their all in a fair and thrilling battle!",
    (2,16,148): "Ready... Fight!",
    (2,16,149): "General Taiki has done it! Xros Heart wins the fifth Legend Master match! Living Legend Koromon and Immortal Brave have fallen to the young challengers! Congratulations!",
    (2,16,150): "Battle Master Koromon, how do you feel after battling the challenger?",
    (2,16,151): "Koromon praises the challenger, saying Taiki overturned every expectation and proved himself perfectly suited to guide the Digital World's next great era!",
    (2,16,152): "Thank you, Koromon. We reached this point through the bonds created by you and countless others. I don't feel like a legend, but I'll protect the title everyone entrusted to me.",
    (2,16,153): "A new Legend Master has appeared! General Taiki and Team Xros Heart prove that the Digital World's spirit will never die! Give them one final cheer! Until our next battle—bye-bye, players!",
    (2,16,154): "At the DigiLab, you can create Digimon through DigiFusion, strengthen them with Jogress Up, use Melodies, and change where your Digimon live. Ask me anything!",
    (2,16,155): "No more questions.",
    (2,16,156): "Return to the previous page.",
    (2,16,157): "Tell me about the DigiLab.",
    (2,16,158): "Tell me about the Digimon List.",
    (2,16,159): "About DigiFusion.",
    (2,16,160): "About Jogress Up.",
    (2,16,161): "About Melodies.",
    (2,16,162): "Tell me about Digimon List features.",
    (2,16,163): "About selecting Digimon.",
    (2,16,164): "About moving Digimon.",
    (2,16,165): "About viewing status.",
    (2,16,166): "About converting to a Melody.",
    (2,16,167): "Tell me about the party.",
    (2,16,168): "Tell me about the DigiBank.",
    (2,16,169): "Tell me about Exploration Teams.",
    (2,16,170): "DigiFusion uses a DigiScore to create a new Digimon from other Digimon. Each recipe has level and stat requirements. Blue and red symbols show which DigiScore type is needed. Collect DigiScores to create many Digimon!",
    (2,16,171): "If a Digimon has reached its level limit, use Jogress Up. The resulting Digimon returns to Level 1 but can grow stronger than before. Its limits are based on the strongest material Digimon. Combining uneven partners may reduce stats. Both must be at least Level 15.",
    (2,16,172): "Melodies are data used to strengthen Digimon. Higher-quality Melodies give greater benefits. You can use up to ten Melodies at once.",
    (2,16,173): "Use the Digimon List to move Digimon among your party, Farm Islands, and other locations. Use it whenever you want to add a farm Digimon to your party.",
    (2,16,174): "View Status shows a Digimon's stats, skills, traits, EXP needed for the next level, and other useful data. Check it when planning battles and development.",
    (2,16,175): "You can convert a Digimon back into Melody data. Be careful before confirming!",
    (2,16,176): "The Digimon traveling with Taiki form the party. You can assign up to nine Digimon. Ask Guilmon for more details!",
})

# Batch 3D: global prose records 3377-3482 (2,072 draft-English words).
OVERRIDES.update({
    (2,16,177): "The DigiBank stores Digimon, but they do not grow while deposited. Put Digimon you want to raise in your party or on a Farm Island. You can keep up to 80 Digimon total.",
    (2,16,178): "Digimon assigned to Exploration Teams search for useful things, including rare items and Melodies unavailable elsewhere.",
    (2,16,179): "The DigiFarm contains Farm Islands where Digimon can grow. Ask about any Farm Island feature.",
    (2,16,180): "No more questions.", (2,16,181): "Return to the previous page.",
    (2,16,182): "Tell me about Training and Jobs.", (2,16,183): "Tell me about Farm Islands.",
    (2,16,184): "Tell me about DigiReports.", (2,16,185): "About Training.",
    (2,16,186): "About Jobs.", (2,16,187): "About Farm Islands.",
    (2,16,188): "About Farm Goods.", (2,16,189): "About Terrain and BGM Boards.",
    (2,16,190): "About DigiReports.", (2,16,191): "About replacing moves.",
    (2,16,192): "Training with Farm Goods raises a Digimon's stats. Seven can be improved: HP, MP, Strength, Spirit, Speed, Defense, and EXP. Different Farm Goods affect different stats.",
    (2,16,193): "Certain Farm Goods let Digimon perform Jobs. Jobs raise stats and can produce items unavailable in shops.",
    (2,16,194): "Each Farm Island holds up to eight Digimon and six Farm Goods. Restoring Capacitor Towers increases the number of available islands, up to six.",
    (2,16,195): "A Farm Island can hold six Farm Goods, purchased at the shop. Each improves different stats, so choose goods suited to the Digimon living there.",
    (2,16,196): "Terrain and BGM Boards greatly affect daily EXP. There are nine of each. Match them to the Digimon on the island for better growth. Boards can be purchased at the shop.",
    (2,16,197): "DigiReports summarize each day's Farm Island and Exploration Team activity: events, created or discovered items, stat gains, and level-ups. Check them often so you don't miss a Digimon reaching its level limit.",
    (2,16,198): "A Digimon can remember four moves. When it learns another, choose one to replace. If a party Digimon has a move pending, the replacement screen appears after the DigiReport.",
    (2,16,199): "I can explain battles! What would you like to know?",
    (2,17,0): "No more questions.", (2,17,1): "Return to the previous page.",
    (2,17,2): "Tell me about strategy.", (2,17,3): "Tell me about moves.",
    (2,17,4): "Tell me about other topics.", (2,17,5): "Tell me about commands.",
    (2,17,6): "Tell me about formations.", (2,17,7): "About status conditions.",
    (2,17,8): "About special effects.", (2,17,9): "About Melody Hooks.",
    (2,17,10): "Tell me about attributes.", (2,17,11): "About earned EXP.",
    (2,17,12): "About the Strategy command.", (2,17,13): "About selecting moves.",
    (2,17,14): "About other commands.", (2,17,15): "About the Vanguard.",
    (2,17,16): "About the Rearguard.", (2,17,17): "About Reserves.",
    (2,17,18): "About Full Power and Conserve.", (2,17,19): "About Guard and Escape.",
    (2,17,20): "About All Strategy.", (2,17,21): "About Move.",
    (2,17,22): "About DigiXros.", (2,17,23): "About Formation.",
    (2,17,24): "About Items.",
    (2,17,25): "Full Power makes a Digimon fight aggressively, choosing its most damaging available move. Conserve favors moves that spend less MP.",
    (2,17,26): "Guard reduces incoming damage. Escape attempts to flee; the battle ends if at least one Digimon escapes successfully.",
    (2,17,27): "All Strategy applies the same strategy to every Vanguard and Rearguard Digimon.",
    (2,17,28): "Choose Move to use a special move. Moves may attack or support. Striking a weakness deals extra damage. Strength-based moves use Strength; Spirit-based moves use Spirit; mixed moves use both.",
    (2,17,29): "Choose DigiXros to use a combination move. Every required Digimon must be in the party and free of disabling status conditions.",
    (2,17,30): "Choose Formation to swap the selected Digimon with another party member.",
    (2,17,31): "Choose Item to restore HP or MP, cure status conditions, or revive a fallen Digimon.",
    (2,17,32): "Vanguard Digimon fight at the front and protect those behind them. Only Vanguard Digimon can perform DigiXros.",
    (2,17,33): "Rearguard Digimon are protected by the Vanguard but deal less damage. If every Vanguard falls, the Rearguard moves forward. At least one Digimon must be assigned to the Vanguard.",
    (2,17,34): "Reserve Digimon also earn EXP, but they cannot replace a defeated battle formation. If every Vanguard and Rearguard Digimon falls, the battle is lost.",
    (2,17,35): "Status conditions include paralysis, sleep, blindness, and others. Cure them with appropriate items or Digimon moves.",
    (2,17,36): "Moves may have special effects. Drain restores HP or MP based on damage dealt. Poison causes ongoing damage. Curse can sharply reduce stats. Some effects may fail.",
    (2,17,37): "Melody Hook can convert defeated wild Digimon into Melody data. Defeat a compatible target using a hooking move for a chance to obtain its Melody.",
    (2,17,38): "Every Digimon has strong and weak attributes. Resistant attacks deal much less damage; weaknesses deal much more. Check move attributes before attacking.",
    (2,17,39): "Every eligible party member shares battle EXP. The more Digimon in the party, the less each receives. Use a smaller party when you want to raise one Digimon quickly.",
    (2,17,40): "I'm the expert! What would you like to ask?",
    (2,17,41): "No more questions.", (2,17,42): "Return to the previous page.",
    (2,17,43): "Tell me about Sky Fort.", (2,17,44): "Tell me about the Xros Loader.",
    (2,17,45): "Tell me about useful features.", (2,17,46): "About Sky Fort facilities.",
    (2,17,47): "About the Command Room.", (2,17,48): "About the Central Room.",
    (2,17,49): "How to raise Digimon.", (2,17,50): "How to protect allies.",
    (2,17,51): "How to change the party.", (2,17,52): "When a level reaches MAX.",
    (2,17,53): "How to obtain strong items.", (2,17,54): "How to earn lots of bits.",
    (2,17,55): "About flying Digimon.", (2,17,56): "About the Service Counter.",
    (2,17,57): "About the Quest Monitor.", (2,17,58): "About Recovery Beds.",
    (2,17,59): "Tell me about saving.", (2,17,60): "About the DigiLab.",
    (2,17,61): "About the DigiFarm.", (2,17,62): "Check party details.",
    (2,17,63): "View all recruited Digimon.", (2,17,64): "View the Digimon Encyclopedia.",
    (2,17,65): "View your items.", (2,17,66): "View collected maps.",
    (2,17,67): "Check active quests.", (2,17,68): "Organize moves.",
    (2,17,69): "Equip an item.", (2,17,70): "Change the formation.",
    (2,17,71): "Flying Digimon carry you to airports in other areas. You must unlock an airport before traveling there. Its key is hidden in a treasure chest, so search carefully!",
    (2,17,72): "At the Service Counter, enter secret passwords, redeem Digimon Reload items, or use tickets to summon Support Digimon. Summoned supporters give you items.",
    (2,17,73): "The Quest Monitor beside Palmon lists requests from Digimon throughout the El Est Zone. More quests appear as you progress. You can review details on the Xros Loader and receive rewards after completion.",
    (2,17,74): "Recovery Beds fully restore HP and MP and cure status conditions. You can find one here and another inside tents. Use them before difficult battles.",
    (2,17,75): "Save at any time using a Save Terminal. On stages, find a Tent Point when you need to save.",
    (2,17,76): "The DigiLab lets you fuse and strengthen Digimon or convert them into Melody data. Ask Veemon near the DigiLab PC for details.",
    (2,17,77): "The DigiFarm helps Digimon grow stronger. Ask Agumon near the Farm PC for details.",
    (2,17,78): "Choose Status on the Xros Loader to inspect the nine Digimon in your party, including HP, conditions, stats, and moves.",
    (2,17,79): "Choose Journey, then Recruited Digimon, to view every Digimon you've befriended along with their moves and traits.",
    (2,17,80): "Choose Journey, then Digimon Encyclopedia, to view discovered Digimon, their moves and traits, and the items they may drop.",
    (2,17,81): "Choose Items on the Xros Loader to view and use everything you are carrying.",
    (2,17,82): "Choose Map to view the world map. Finding maps in treasure chests adds detail. On a stage, press SELECT to see the current area and your position. Areas without a collected map remain hidden.",
})

# Batch 3E: global prose records 3483-3549 (2,021 draft-English words).
OVERRIDES.update({
    (2,17,83): "Choose Journey, then Quest, on the Xros Loader to review accepted quests. If you're unsure what to do next, check Quest Information.",
    (2,17,84): "Choose Moves on the Xros Loader to organize party Digimon moves. Place frequently used moves where they're easy to select. You can also review field skills here.",
    (2,17,85): "Choose Equipment to equip or remove party items. Raise Strength for Strength moves and Spirit for Spirit moves. Mixed moves benefit from both. Defense and Spirit reduce incoming damage.",
    (2,17,86): "Choose Formation to rearrange party Digimon. Reserve Digimon also earn EXP, so place Digimon you want to raise there.",
    (2,17,87): "When a Digimon reaches its level limit, use Jogress Up to raise its potential. Combining similarly developed Digimon gives better results. Ask Veemon near the DigiLab PC for details.",
    (2,17,88): "Powerful items come from treasure, quests, and Farm Jobs. Buy Job Farm Goods, place them on an island, and assign Digimon to work. Stronger Digimon can make stronger items. Ask Agumon for details.",
    (2,17,89): "Sell unwanted items when you need bits. Exploration Teams may find coins, gems, netsuke, and other valuables meant for selling. Penmon pays well for them. Ask Agumon about Exploration Teams.",
    (2,17,90): "I can explain the communication features available through the Communication Box beside me.",
    (2,17,91): "No more questions.", (2,17,92): "About Melody Exchange.",
    (2,17,93): "About sending DigiScores.", (2,17,94): "About receiving DigiScores.",
    (2,17,95): "Choose Melody Exchange to trade one Melody with a friend. The Melody you send is consumed. Some Melodies cannot be exchanged; choose another if the transfer fails.",
    (2,17,96): "You can send a DigiScore to a friend without losing your own copy. Some DigiScores cannot be sent; choose another if the transfer fails.",
    (2,17,97): "Choose Receive DigiScore to obtain one from a friend. You cannot receive a DigiScore you already possess; select another instead.",
    (2,17,98): "Shh! Keep it down! I heard the legendary Weapon Digimon is here, so I've been staking this place out. Stay quiet and I'll show you something cool!",
    (2,17,99): "Watch something cool?", (2,17,100): "Yes, show me.",
    (2,17,101): "No, thanks.", (2,17,102): "Not right now?",
    (2,17,103): "Come back anytime you want to see it. I'll return to my stakeout!",
    (2,17,104): "All right, watch closely.", (2,17,105): "Okay! Hold still!",
    (2,17,106): "Well? Pretty fun, right? Come back again!",
    (2,17,107): "Huh? That's strange. You can normally save here. Is the Save Terminal broken?",
    (2,17,108): "Huh? That's strange. You can normally save here. Is the Save Terminal broken?",
    (2,17,109): "Welcome! I'm Tentomon, caretaker of this tent. Tentomon in a tent—get it? Anyway, nice to meet you!",
    (2,17,110): "Remember how to use the bed and Save Terminal. Press A beside the bed to restore every Digimon's HP and MP. Press A beside the terminal to save—though this one isn't working right now. Sorry!",
    (2,17,111): "Thanks for helping me. You're a good person, aren't you? I've never met a human before, much less a General. I heard rumors, but I never thought you really existed.",
    (2,17,112): "You defeated that frightening Digimon? Amazing! Are you amazing because you're a General, or a General because you're amazing?",
    (2,17,113): "Approach a ladder and press the A Button to climb up or down.",
    (2,17,114): "This is a Tent Point. Press the A Button here to open your tent. Inside, you can restore HP and MP and save.",
    (2,17,115): "This is a Tent Point. Press the A Button at its marker to open your tent. Tents are key facilities, so use them often.",
    (2,17,116): "Access the nearby PC to use the DigiFarm and raise Digimon.",
    (2,17,117): "Access the nearby PC to use the DigiLab and strengthen Digimon.",
    (2,17,118): "Welcome! I'm Tentomon, the caretaker. Press A beside the bed to fully restore your Digimon. Press A beside the Save Terminal to save. Easy, right?",
    (2,17,119): "Tentomon in a tent! Get it? Anyway, nice to meet you!",
    (2,17,120): "Approach a ladder and press the A Button to climb up or down.",
    (2,17,121): "Approach a ladder and press the A Button to climb up or down.",
    (2,17,122): "...",
    (2,17,123): "Welcome back! Save your adventure by pressing A beside the Save Terminal. When your Digimon's HP or MP is low, press A beside the bed.",
    (2,17,124): "Saving frequently is the key to a smooth adventure.",
    (2,17,125): "I'm so glad everyone came! Only ROG's leader, Minotaurmon, remains. He's in the Command Room next door!",
    (2,17,126): "Thank you for helping us! Please take care of Spadamon.",
    (2,17,127): "We have to rescue your friends! The Central Room is farther inside!",
    (2,17,128): "It's Tentomon, your familiar tent caretaker! Press A beside the Save Terminal to save and A beside the bed to restore HP and MP. Simple, right?",
    (2,17,129): "Once a Capacitor Tower activates, the DigiFarm starts working and DigiReports become available. They contain lots of useful data, so check them.",
    (2,17,130): "Sky Fort was built to protect this Zone. Long ago, many guardians lived here, and the Quest Monitor has existed since their time.",
    (2,17,131): "The Quest Monitor is the large screen in the Command Room. Ask Palmon beside it for instructions.",
    (2,17,132): "Go to the Skyport in front of the Command Room and speak to a flying Digimon. Fly to West Knuckle Coast, enter WK City, and activate the Capacitor System inside its tower.",
    (2,17,133): "Thanks for activating the Capacitor Tower, Taiki! The DigiLab and DigiFarm PCs are available now. Ask Veemon and Agumon for details. Please restore the remaining towers too!",
    (2,17,134): "I hope Chibickmon is safe. He's tiny, so he may have fallen into a nearby hole. Bring a Digimon with the Dig field skill—Dorumon from Fort Yard or Guilmon from Knuckle Coast can learn it.",
    (2,17,135): "I hope Chibickmon is safe. He's tiny, so he may have fallen into a nearby hole. Bring Armadillomon from Fort Yard; it can learn the Dig field skill.",
    (2,17,136): "I'm glad you found Chibickmon, but he gave you the key to western Spiral Amazon. That means trouble is waiting there. Be careful, Taiki.",
    (2,17,137): "Did you know holes aren't the only field-skill points? Spiral Amazon has a Digital Route, so look for a portal somewhere nearby!",
    (2,17,138): "Taiki, have you opened the airport gates? After activating a city's Capacitor Tower, remember to unlock its airport too!",
    (2,17,139): "If you get lost, check the area map by pressing SELECT or choosing Map on the Xros Loader. Areas remain hidden until you obtain their map.",
    (2,17,140): "Did you obtain the Cloud Ruins key? It should open the way forward after the Papyrus battle.",
    (2,17,141): "There aren't any sweets in Crystal Volcano... and Spadamon doesn't have any either.",
    (2,17,142): "Sky Fort's number-one Item Shop, run by Penmon! Well, it's also the only shop here.",
    (2,17,143): "Thank you for restoring Sky Fort! I want to support everyone too, so talk to me whenever you need help.",
    (2,17,144): "Thank you for restoring Sky Fort! I want to support everyone too, so talk to me whenever you need help.",
    (2,17,145): "Do your best, Taiki, but don't push yourself too hard. I know you can't ignore someone in trouble, but you can't help anyone if you collapse. Got it?",
    (2,17,146): "The Quest Monitor is in the room where Minotaurmon was. Palmon, the green Digimon beside it, will explain how it works.",
    (2,17,147): "Flying Digimon can take you to many places. For now, only West Knuckle Coast is available. Find keys and open more airport gates to unlock new destinations.",
    (2,17,148): "Taiki, are you checking the area map? It shows your location on the current stage.",
    (2,17,149): "Chibickmon is strong in a group, but helpless alone. Taiki, please find him quickly!",
})

# Batch 3F: global prose records 3550-3629 (2,008 draft-English words).
OVERRIDES.update({
    (2,17,150): "\"No kyup-kyup here\"...? What's that supposed to mean? A message from Chibickmon? Don't ask me. Maybe Cutemon isn't cute? If so, you'd better watch out!",
    (2,17,151): "I'm glad you found Cutemon and Dorulumon! That's Taiki for you. Keep restoring the remaining Capacitor Towers!",
    (2,17,152): "What?! An explosion in Digital Space, and Sparrowmon's SOS? Taiki, are you okay? Don't do anything reckless.",
    (2,17,153): "You're heading to the Cloud Ruins next? Sparrowmon may be trapped there. Good luck, Taiki—but please be careful!",
    (2,17,154): "Sparrowmon made it back! That's Taiki for you!",
    (2,17,155): "ROG is probably at Earth Fort in Crystal Volcano. I have a bad feeling. Taiki, don't do anything reckless!",
    (2,17,156): "This place is called Sky Fort? A fortress in the sky... That's incredible! And really cool!",
    (2,17,157): "Zenjirou Tsurugi, Commander of Sky Fort, orders you to find a flying Digimon immediately! I'm counting on you, General Taiki! Wait—which title outranks the other?",
    (2,17,158): "Listen carefully! Every Move and DigiXros uses different stats for damage. Check the icon beside its name: Strength uses Strength, Spirit uses Spirit, and mixed uses both. Remember that and you'll fight much better!",
    (2,17,159): "Treasure appears on the area map as TREASURE. Searching for it is a man's romance!",
    (2,17,160): "Was Chibickmon really kidnapped? He's such a carefree little guy. Maybe this isn't as serious as everyone thinks.",
    (2,17,161): "Chibickmon's key seems to point toward the far west of Spiral Amazon.",
    (2,17,162): "We'll look after Cutemon. You focus on defeating ROG and restoring the other Capacitor Towers. I'm counting on you, Taiki Kudo!",
    (2,17,163): "Sparrowmon called Taiki for help? Then we have to move now! But Taiki keeps picking up SOS signals from everywhere...",
    (2,17,164): "You're growing stronger, Taiki, so you need stronger equipment. Buy Weapon Workshop and Armor Workshop Farm Goods from BomberNanimon in East Knuckle City, then assign Farm Jobs to craft equipment.",
    (2,17,165): "I heard a strange rumor about Papyrus Judgment: anyone who enters is afflicted by Pharaohmon's curse. Prepare for cursed enemies, especially mummies.",
    (2,17,166): "Taiki Kudo, did you activate all six Capacitor Towers? If you did, the DigiFarm should have six Farm Islands. Don't tell me you still have fewer than six!",
    (2,17,167): "Thanks for helping! Even Dorulumon seems less irritable now.",
    (2,17,168): "ROG's Minervamon was an enemy, but... she was kind to me.",
    (2,17,169): "After Jogress Up or DigiFusion, resulting Digimon are sent to the DigiBank. Remember, Digimon stored there do not earn EXP.",
    (2,17,170): "Are you assigning Digimon to Exploration Teams? They'll gather items for you. Larger teams can bring back more finds.",
    (2,17,171): "Everyone's happy Sparrowmon returned. Great work, Taiki!",
    (2,17,172): "After accepting a quest from the Quest Monitor, check Quest on the Xros Loader. It's really convenient!",
    (2,17,173): "Hi, Taiki! I'm Palmon. Press A beside the monitor to access it, then choose an available request from the Quest List. Select View Details before accepting if you want more information.",
})
for _index in range(174, 184):
    OVERRIDES[(2,17,_index)] = "To cancel an accepted quest, open Quest on the Xros Loader and select that quest again."
OVERRIDES.update({
    (2,17,184): "Taiki, this is the Service Counter. Bring me a ticket whenever you want to summon a Digimon!",
    (2,17,185): "We're starting to look like real superheroes. What do we do now?",
    (2,17,186): "Everyone is asking for our help. Let's grant Digimon's wishes through the Quest Monitor, one small job at a time!",
    (2,17,187): "Go! Keep going! Don't give up! Head for the tower! Uh... I forgot which tower.",
    (2,17,188): "I've got it now! Go where the energy is strongest and activate the Capacitor Tower switch! Right?",
    (2,17,189): "Taiki, please find Chibickmon! We really need him!",
    (2,17,190): "Thanks, big brother! We were so worried. Now that Chibickmon is back, I can finally relax!",
    (2,17,191): "Chibickmon, Dorulumon, and Cutemon are back. One by one, our worries are disappearing.",
    (2,17,192): "Sparrowmon is at the Cloud Ruins? Then we need to find the key that opens the ruins.",
    (2,17,193): "You found the key, right? Then Sparrowmon can't be far away. Good luck, big brother!",
    (2,17,194): "Sparrowmon came back, but doesn't remember what happened. Still, you did a great job, big brother!",
    (2,17,195): "Digimon throughout this Zone need help. Check the Quest Monitor whenever you have time, big brother!",
    (2,17,196): "Taiki, are you doing your best?",
    (2,17,197): "Taiki, listen to everyone's requests! Check the Quest Monitor!",
    (2,17,198): "Taiki, are you going to the Capacitor Tower? Pipismon wants to come too!",
    (2,17,199): "Taiki, what happened at the Capacitor Tower? Huh? Something about interference and radio waves?",
    (2,18,0): "Where did Taiki go? Pipismon doesn't really understand. Do you?",
    (2,18,1): "What's wrong, Taiki? Can't find the way through Spiral Amazon? The entrance was inside a hollow log.",
    (2,18,2): "SuperStarmon can't get out? Hurry and help him, Taiki!",
    (2,18,3): "Did you find SuperStarmon and the key? Please hurry and rescue him!",
    (2,18,4): "SuperStarmon is back! Taiki is amazing. Everyone's so happy!",
    (2,18,5): "Taiki, listen to everyone's requests! Check the Quest Monitor!",
    (2,18,6): "Are we really supposed to be heroes? Digimon around here are counting on us!",
    (2,18,7): "Looks like we're expected to save the whole world.",
    (2,18,8): "We're headed for some kind of tower, right? Oh, the Capacitor Tower! Leaving it alone would be bad.",
    (2,18,9): "There are six Capacitor Towers supplying energy. Activate even one and Sky Fort's systems should begin coming back online.",
    (2,18,10): "We still don't know where Chibickmon is. If he's nearby, maybe he'll answer when we call.",
    (2,18,11): "Everyone's relieved Chibickmon returned. I am too. Thanks, big brother!",
    (2,18,12): "I don't understand Minervamon. She says she only took Chibickmon because he was cute.",
    (2,18,13): "Did you find Sparrowmon? No, only a voice calling for help? If Taiki heard it, I'm sure it was real. You'll find Sparrowmon!",
    (2,18,14): "I heard Sparrowmon is badly damaged and can't move. What could have happened?",
    (2,18,15): "Sparrowmon returned but doesn't remember anything. What a mess.",
    (2,18,16): "What's wrong, big brother? Unsure what to do? It'll work out somehow, so don't worry!",
    (2,18,17): "That's a fine-looking party. If you recruit me, I'll prove useful. Talk to me whenever you feel like it!",
    (2,18,18): "What an interesting group! Would you let me join? I can't say why yet, but talk to me anytime and I'll become your ally.",
    (2,18,19): "What an impressive party! Let me join too. Talk to me now and I'll come right away!",
    (2,18,20): "That's a fine-looking party. If you recruit me, I'll prove useful. Talk to me whenever you feel like it!",
    (2,18,21): "I'll remove the troublesome Digimon! Piko... piko! The nuisance is gone! A new quest has been posted to the Quest Monitor!",
    (2,18,22): "A new quest has been posted to the Quest Monitor!",
    (2,18,23): "Welcome to Penmon's West Knuckle City Item Shop! We carry wonderfully useful items!",
    (2,18,24): "Taiki, this is the Service Counter. Bring me a ticket whenever you want to summon a Digimon!",
    (2,18,25): "Welcome to the West Knuckle City Farm Shop! Boom! Blast! Bomber!",
    (2,18,26): "I thought we'd never return. When ROG seized Sky Fort, I thought everything was over. Thank you, Taiki and Spadamon!",
    (2,18,27): "Your little friend was kidnapped? I saw a tiny triangular Digimon following someone near the Capacitor Tower. They seemed headed toward Spiral Amazon.",
    (2,18,28): "You found the little Digimon? That's good. He vanished because... you were playing hide-and-seek? So it wasn't a kidnapping after all.",
    (2,18,29): "You found the rest of your separated friends too? Good. The more friends you have, the stronger you become. Friendship matters.",
})

# Batch 3G: global prose records 3630-3714 (2,014 draft-English words).
OVERRIDES.update({
    (2,18,30): "Did you learn where your friend is being held? Then you'll probably find them soon. This Zone doesn't have many places suitable for a prison.",
    (2,18,31): "Still haven't found your friend? You located the prison? Then you're getting close.",
    (2,18,32): "You finally rescued your imprisoned friend. You guys really are something.",
    (2,18,33): "Looking for Earth Fort? Isn't it right over there? I understand a fort on land or water, but not one in the sky.",
    (2,18,34): "Welcome to Penmon's East Knuckle City Item Shop! The E stands for excellent! Or maybe east.",
    (2,18,36): "Welcome to East Knuckle City's Farm Shop! Yeah! Want some? Bomber!",
})
for _index in (35,45,53,66,73,89,97,102,107,112):
    OVERRIDES[(2,18,_index)] = "Taiki, this is the Service Counter. Bring me a ticket whenever you want to summon a Digimon!"
_weapon_tip = "Thanks for driving out ROG! Here's a tip: buy the Weapon Workshop from BomberNanimon, place it on a Farm Island, and assign a Digimon to work. It can craft powerful weapons!"
for _index in range(37,42):
    OVERRIDES[(2,18,_index)] = _weapon_tip
OVERRIDES.update({
    (2,18,42): "Thanks for driving out ROG! Your strength amazed me. I hope the rest of ROG leaves this Zone for good.",
    (2,18,43): "Thanks for driving out ROG, Taiki! You've helped us so much. One more favor: check Sky Fort's Quest Monitor. Plenty of others still need help!",
    (2,18,44): "Welcome to Penmon's Spiral City Item Shop! Even if you're lost, good items keep you prepared.",
    (2,18,46): "Welcome to Spiral City's Farm Shop! Yeah! Need it? Bomber!",
    (2,18,47): "Thank you for reclaiming the Capacitor Tower! You've been a huge help!",
    (2,18,48): "Taiki, Spadamon, thank you! The Cloud Ruins key? Sorry, I don't have it. I wish I could help.",
    (2,18,49): "Thank you for reclaiming the Capacitor Tower! You've been a huge help!",
    (2,18,50): "Thank you for reclaiming the Capacitor Tower! You've been a huge help!",
    (2,18,51): "Thank you! I'm happy to be home. Earth Fort? I don't know anything about it. Sky Fort, sure, but not Earth Fort.",
    (2,18,52): "Welcome to Penmon's Skull City Item Shop! The city may look dangerous, but the shop is perfectly safe.",
    (2,18,54): "Welcome to Skull City's Farm Shop! Yeah! Rock it! Bomber!",
    (2,18,55): "Taiki, thank you for coming all this way to help! This area is full of joy again.",
    (2,18,56): "Taiki, thank you for coming all this way to help! This area is full of joy again.",
    (2,18,57): "Thanks for helping, Taiki! If possible, help the others too. Their wishes should appear on the Quest Monitor. I'm counting on you!",
    (2,18,58): "I never thought we'd return here. Thank you so much, Taiki!",
    (2,18,59): "I never thought we'd return here. Thank you so much, Taiki!",
    (2,18,60): "Thank you for everything, Taiki! Let me know if you're ever in trouble. Crystal Volcano? That sounds far too hot for me!",
    (2,18,61): "Hoge! Listen to my song, hoge! Don't leave until it's finished! I am Lord Glacier, eternal singer of the frozen peaks! Lord Volcano and Lord Glacier together are the Lords, hoge!",
    (2,18,62): "Nobody can stop the Lords' song, hoge! Only earthquakes, thunder, volcanic eruptions, smoke, and my mother can stop it, hoge!",
    (2,18,63): "I'll remove the troublesome Digimon! Piko... piko! The nuisance is gone! A new quest has been posted to the Quest Monitor!",
    (2,18,64): "A new quest has been posted to the Quest Monitor!",
    (2,18,65): "Welcome to Penmon's Cloud City Item Shop! Even among the clouds, our stock is down-to-earth.",
    (2,18,67): "Welcome to Cloud City's Farm Shop! Yeah! Whoa! Bomber!",
    (2,18,68): "I heard someone was reclaiming Capacitor Towers from ROG, but I never imagined the rumors were true! I'm shaking with excitement! Ah-ha-ha-ha!",
    (2,18,69): "You've come to save this Zone? Everyone looks hopeful again. Please help us, heroes!",
    (2,18,70): "Taiki, I'll tell you something useful as thanks, Pino! If you're stuck at Papyrus Judgment, open the huge door. Once it's open, push ahead with everything you've got, Pino!",
    (2,18,71): "You're the hero of this Zone, Pino! That's why I want you to grant wishes through the Quest Monitor, Pino!",
    (2,18,72): "Welcome to Penmon's Papyrus City Item Shop! No need to hold back—buy as much as you like!",
    (2,18,74): "Welcome to Papyrus City's Farm Shop! Yeah! Get it! Bomber!",
    (2,18,75): "I couldn't protect this place, even though I was supposed to be this Zone's guardian...",
    (2,18,76): "Leave tents to me! Press A beside the Save Terminal to save your adventure, and A beside the bed to restore your Digimon's HP and MP. Easy, right?",
    (2,18,77): "Have you been reading your DigiReports? They're packed with useful information. You can even win the Report Lottery after reviewing one!",
    (2,18,78): "Before Sky Fort existed, Earth Fort protected this Zone. Its radar should still be able to scan the entire area. ZDMillenniummon may be using it to search for something.",
    (2,18,79): "Taiki! Defeat ROG before ZDMillenniummon finds whatever it's searching for!",
    (2,18,80): "Welcome to Sky Fort's famous Penmon Item Shop—also known as the Sky Shop! Pretty cool, right?",
    (2,18,81): "We've been thinking about how to help, but there isn't much we can do in a fight against ROG. We'd only get in your way.",
    (2,18,82): "We don't have much to offer, but we're always cheering for Taiki and the others. Please remember that.",
    (2,18,83): "I want to fight ROG beside you, but leaving Sky Fort undefended would be dangerous. We'll strengthen its defenses.",
    (2,18,84): "Leave defense to me, and I'll leave offense to you. Good luck, Taiki!",
    (2,18,85): "You're about to face a powerful enemy, but I'm sure Taiki can handle it.",
    (2,18,86): "Things have almost never turned out okay before, but with Taiki and the others, I'm certain they will!",
    (2,18,87): "Welcome, Taiki. This is the Quest Monitor—but you already know that. Thanks for always helping. Please keep it up!",
    (2,18,88): "Your final battle with ROG is near. If you need a change of pace before then, check the Quest Monitor.",
    (2,18,90): "You're going to defeat ROG's boss, right? We get to help too... don't we?",
    (2,18,91): "Woo-hoo! Let's do it! We'll blast ROG's boss sky-high!",
    (2,18,92): "Taiki, are you doing your best? Pipismon is cute! Pipismon will do its best too!",
    (2,18,93): "Pipismon, stay safe. It's going to be scary, but everyone will look so cool!",
    (2,18,94): "Hey, Taiki. How are you holding up? If you push too hard, you'll exhaust yourself. Learn when to relax too.",
    (2,18,95): "High HP won't help if your MP is empty. Basic attacks still work, but without enough HP you'll fall before you can win.",
    (2,18,96): "Welcome to West Knuckle City's famous Penmon Item Shop—the Double Shop! There's nothing double about it!",
    (2,18,98): "Welcome to West Knuckle City's Farm Shop! Yeah! Love it! Bomber!",
    (2,18,99): "You helped our people one after another. No amount of thanks could ever be enough.",
    (2,18,100): "We may never be able to repay you, but every Digimon in this Zone is truly grateful.",
    (2,18,101): "Welcome to East Knuckle City's famous Penmon Item Shop—the E-Shop! What does E mean? Who knows!",
    (2,18,103): "Welcome to East Knuckle City's Farm Shop! Yeah! Want some? Bomber!",
    (2,18,104): "You're fighting ROG's boss, ZDMillenniummon? I can hardly believe it. Still, you guys can do it. Good luck, Taiki!",
    (2,18,105): "You don't need me to tell you, but don't rush. Take it one step at a time!",
    (2,18,106): "Welcome to Spiral City's famous Penmon Item Shop—the Spiral Shop! Careful, the name may make you dizzy!",
    (2,18,108): "Welcome to Spiral City's Farm Shop! Yeah! Need it? Bomber!",
    (2,18,109): "I heard you're fighting ROG's leader, Taiki. You're incredible—and seriously cool!",
    (2,18,110): "ROG's leader is extremely strong. Don't lose—keep fighting to the end!",
    (2,18,111): "Welcome to Skull City's famous Penmon Item Shop—the Skull Shop! That one actually makes sense!",
    (2,18,113): "Welcome to Skull City's Farm Shop! Yeah! Rock it! Bomber!",
    (2,18,114): "We're all grateful to you, and we're happy to be together again!",
})

# Batch 3H: global prose records 3715-3796 (2,009 draft-English words).
OVERRIDES.update({
    (2,18,115): "Hurray! Hurray! Go, team! Wait... who exactly is Ray?",
    (2,18,116): "Everyone had given up on this endless fight, but Taiki and the others changed us. We have hope again. Thank you, Taiki!",
    (2,18,117): "Thanks to Taiki and the others, we can live here again. We're truly grateful and will keep supporting you!",
    (2,18,118): "Welcome to Cloud City's famous Penmon Item Shop—the Cloud Shop! Wait, that sounds like it isn't really here...",
    (2,18,120): "Welcome to Cloud City's Farm Shop! Yeah! Whoa! Bomber!",
    (2,18,121): "Crystal Volcano? Earth Fort? What a nostalgic name. Long ago, the guardians who protected this Zone gathered there.",
    (2,18,122): "Hero of the El Est Zone! Are you doing your best? Of course you are!",
    (2,18,123): "I've heard so many good rumors about you, Pino! Digimon everywhere are happy, Pino!",
    (2,18,124): "I know how hard you're working for this Zone, Pino. Don't push yourself until you collapse. We're always cheering for you!",
    (2,18,125): "Welcome to Papyrus City's famous Penmon Item Shop—the Papyrus Shop! That's a mouthful!",
    (2,18,127): "Welcome to Papyrus City's Farm Shop! Yeah! Get it! Bomber!",
    (2,18,128): "Still working hard as always? We'll do our best so we don't fall behind!",
    (2,18,129): "This Zone's future rests on your shoulders. I know that's a heavy burden, but please keep going!",
    (2,18,130): "Hoge! Listen to my song, hoge! Don't leave until it ends! I am Lord Volcano, endless rocker of the fiery peaks! Lord Volcano and Lord Glacier together are the Lords, hoge!",
    (2,18,131): "Nobody can stop the Lords' song, hoge! Only earthquakes, thunder, volcanic eruptions, smoke, and my mother can stop it, hoge!",
    (2,18,132): "Welcome! I'm Tentomon. You know the bed and Save Terminal already, so check out the new DigiLab and DigiFarm PCs inside this tent!",
    (2,18,133): "The DigiLab and DigiFarm work just like Sky Fort's. Use them well and keep up the good work!",
    (2,18,134): "Taiki! You came to help! Thank you! ROG ignored us and rushed straight toward the Sky Garden!",
    (2,18,135): "Sky Fort's number-one Penmon Item Shop! Well, it's also the only shop here.",
    (2,18,136): "Taiki, once this Zone is safe, come back and tell me everything that happened. Promise you'll return.",
    (2,18,137): "There's little left for me to say. Please protect the El Est Zone!",
    (2,18,138): "We're all going to make a fresh start now. I feel like I've heard that somewhere before.",
    (2,18,139): "Taiki! I'm glad you're okay. I knew you could handle it, but everyone was worried. Actually, maybe we were the ones causing trouble...",
    (2,18,141): "Let's go! Our friends are waiting, and I'm sure they're in trouble!",
    (2,18,142): "Taiki, what's wrong? Pipismon heard something strange...",
    (2,18,143): "Something feels wrong. Don't let your guard down, Taiki.",
})
for _index in (119,126,140,145,151,157,163,172,181):
    OVERRIDES[(2,18,_index)] = "Taiki, this is the Service Counter. Bring me a ticket whenever you want to summon a Digimon!"
for _index in (144,150,156,162,171,180):
    OVERRIDES[(2,18,_index)] = "Welcome to the newly rebuilt Penmon Item Shop—recently renovated and fully restocked!"
OVERRIDES.update({
    (2,18,146): "Welcome to West Knuckle City's upgraded Farm Shop! Our selection is better than ever! Yeah! Love it! Bomber!",
    (2,18,147): "When the Shadow Guard seized the tower, I had no choice but to flee. I felt pathetic. Thank you for saving us!",
    (2,18,148): "Someone sent you a mysterious message? I wonder who. Still, you guys can handle danger—you're this Zone's heroes!",
    (2,18,149): "Everyone at Sky Fort seems safe now. What a relief. Taiki, you really are this Zone's hero!",
    (2,18,152): "Welcome to East Knuckle City's upgraded Farm Shop! Our selection is better than ever! Yeah! Want some? Bomber!",
    (2,18,153): "Thank you for defeating the Shadow Guard! I fought until the end but finally had to surrender. You saved us again, and I'm truly grateful.",
    (2,18,154): "You were summoned to Stealth Valley? I've never heard of it. Only the pure of heart can see it? Then I guess I can't help—hey, what does that imply?!",
    (2,18,155): "You finally found ROG's true leader? Only their location, not the leader himself? Then the final battle is close. You can do it!",
    (2,18,158): "Welcome to Spiral City's upgraded Farm Shop! Our selection is better than ever! Yeah! Need it? Bomber!",
    (2,18,159): "Taiki, thanks for saving us again. I keep getting driven out, but your battle will become a legend passed down for generations!",
    (2,18,160): "You were summoned to Stealth Valley? I've heard legends of a hidden place no one can find, where impossible Digimon are said to live.",
    (2,18,161): "You returned to Sky Fort and found everyone safe? Wonderful! Congratulations!",
    (2,18,164): "Welcome to Skull City's upgraded Farm Shop! Our selection is better than ever! Yeah! Rock it! Bomber!",
    (2,18,165): "Thanks to you, we're safe again! I truly wondered what would happen. You saved our lives.",
    (2,18,166): "Stealth Valley? I don't know that area. If it's called Stealth, it must be hidden!",
    (2,18,167): "You can finally return to Sky Fort? That's wonderful. I'm truly relieved.",
    (2,18,168): "Thank you, Taiki! The Shadow Guard appeared without warning and seized the tower almost instantly. We relaxed after ZDMillenniummon fell.",
    (2,18,169): "You're going to Stealth Valley? A secret place nobody knows? I never realized this Zone had somewhere like that.",
    (2,18,170): "You're facing ROG's true leader? You'll be fine. Nobody in this Zone is stronger than Taiki and the others!",
    (2,18,173): "Welcome to Cloud City's upgraded Farm Shop! Our selection is better than ever! Yeah! Whoa! Bomber!",
    (2,18,174): "Thank you for reclaiming the tower, Taiki! We tried to defend it, but they defeated us instantly. Their strength was on another level.",
    (2,18,175): "You still can't return to Sky Fort because the interference remains? Restoring the tower wasn't enough? You'll find a solution!",
    (2,18,176): "You returned to Sky Fort and everyone is safe? Great! But now you must fight ROG's true leader? You can handle it!",
    (2,18,177): "Taiki saved me, Pino! The Shadow Guard appeared and mocked me. I tried to fight but couldn't win, so I had to flee, Pino.",
    (2,18,178): "A seventh Capacitor System in Stealth Valley, Pino? A mysterious person summoned you there? I trust Taiki, but please be careful, Pino.",
    (2,18,179): "The barrier vanished and you returned to Sky Fort? Congratulations, Pino! You worked so hard!",
    (2,18,182): "Welcome to Papyrus City's upgraded Farm Shop! Our selection is better than ever! Yeah! Get it! Bomber!",
    (2,18,183): "Thank you. I lost the tower and failed to reclaim it because they removed the Capacitor System entirely.",
    (2,18,184): "A mysterious person summoned you, Taiki? It could be a trap. Please be careful!",
    (2,18,185): "You're back at Sky Fort, but ROG's true leader isn't there? Don't give up, Taiki. You'll find them somewhere!",
    (2,18,186): "Do your best, Taiki. Everyone is waiting. Remove the interference and return to Sky Fort—Patamon and the others are trapped by Barbamon.",
    (2,18,187): "Switching every tower's Capacitor System out of emergency mode should remove the interference. All six must be changed, and ROG will be guarding them.",
    (2,18,188): "Activating the Capacitor in Stealth Valley should let you reach Sky Fort. The Digimon there are Spadamon's friends, so they'll help, right?",
    (2,18,189): "Do your best, Taiki. Everyone is waiting. Remove the interference and return to Sky Fort—Patamon and the others are trapped by Barbamon.",
    (2,18,190): "Switching every tower's Capacitor System out of emergency mode should remove the interference. All six must be changed, and ROG will be guarding them.",
    (2,18,191): "Activating the Capacitor in Stealth Valley should let you reach Sky Fort. The Digimon there are Spadamon's friends, so they'll help, right?",
    (2,18,192): "Penmon's Item Shop appears even in a place like this! I brought as much stock as I could carry!",
    (2,18,193): "You probably know this already: press A at the Save Terminal to save, the bed to restore HP and MP, the left PC for DigiLab, and the right PC for DigiFarm.",
    (2,18,194): "When something catches your attention, face it and press the A Button.",
    (2,18,195): "The portal to the DigiColosseum opened! I haven't heard that name in ages. It's all thanks to everyone's hard work.",
    (2,18,196): "You're already a Bronze Master? Didn't you only just enter? Ranking up shouldn't be that easy. Taiki and the others really are strong!",
})

# Batch 3I: global prose records 3797-3866 (2,008 draft-English words).
OVERRIDES.update({
    (2,18,197): "Silver Master? Congratulations! You're rising smoothly. Gold may be within reach, and perhaps even Platinum!",
    (2,18,198): "Gold Master?! I knew you were strong, but not this strong. You might really reach Platinum. No—you absolutely can!",
    (2,18,199): "Platinum Master?! Amazing! There are hardly any Platinum Masters. Has the El Est Zone ever produced one before? Xros Heart is incredible!",
    (2,19,0): "Legend Master?! Taiki, how? I thought Legend Masters were only myths—heroes reborn as Digimon after saving the Digital World long ago.",
    (2,19,1): "Thanks for coming! This is Penmon's Sky Fort Item Shop—the Sky Shop!",
    (2,19,2): "Don't give up because the legendary Weapon Digimon vanished, Taiki! Patamon was panicking earlier. Did something happen?",
    (2,19,3): "Bronze Master? The new portal leads to the DigiColosseum? Bronze Master sounds pretty cool!",
    (2,19,4): "Silver Master—the rank above Bronze? There are even higher ranks? Then Gold Master must be next!",
    (2,19,5): "Gold Master! That's Taiki for you. Are you number one in the Digital World now? What, Platinum is higher?",
    (2,19,6): "Platinum Master! Congratulations! So Taiki is at the top—wait, Legend Master is still higher? How many ranks are there?!",
    (2,19,7): "You finally did it, Taiki! No—Taiki the Legend Master! Somehow that fancy title doesn't suit you.",
    (2,19,8): "Our work isn't finished just because the Zone is safe, Taiki Kudo! The Quest Monitor is still full of SOS calls!",
    (2,19,9): "I heard, Taiki Kudo! Bronze Master is only the bottom rank. As your rival, I expect you to climb higher. You can do it!",
    (2,19,10): "Silver Master?! Well done, Taiki Kudo! Is Battle Master Koh from Team Sunburst really strong? I've never heard of him, but those DWM heroes saved Digital Worlds before. Now you're one of them!",
    (2,19,11): "Gold Master? Congratulations! I think that makes you about as strong as Japan's number one. I understand ranks perfectly... probably.",
    (2,19,12): "Platinum Master? Does that mean you've gone from Japan's best to the world's best? If my rival Taiki is number one, then I'll aim for number one too!",
    (2,19,13): "Legend Master? A living legend? Taiki Kudo, haven't you gone too far? If my rival is already a legend, what am I supposed to aim for?",
    (2,19,14): "This Zone is lively again! Taiki worked hard. That's wonderful!",
    (2,19,15): "You became Bronze Master? Great job! But bronze doesn't suit Taiki. You need a higher rank—like Tinplate Master!",
    (2,19,16): "You became Silver Master? Great work, Taiki! Keep aiming higher and show them what Xros Heart's General can do!",
    (2,19,17): "You became Gold Master? Amazing! Gold finally feels worthy of Taiki. It suits you!",
    (2,19,18): "You became Platinum Master? I can hardly believe it. After everything you've overcome, Taiki really is amazing!",
    (2,19,19): "Taiki became Legend Master? That's so incredible, I don't even know what to say!",
    (2,19,20): "Welcome, Taiki. This is the Quest Monitor—but you know that. Thanks for always helping the El Est Zone!",
    (2,19,21): "Welcome back, Taiki. I heard you became Bronze Master at the DigiColosseum. Here's something even luckier: a quest! Granting wishes feels wonderful. How was that for a youthful sales pitch?",
    (2,19,22): "Hi, Taiki! I heard you've become Silver Master. That sounds powerful! I know you're stronger now, but don't push yourself too hard.",
    (2,19,23): "Welcome to my Quest Monitor—yes, mine! Forget I said that. Gold Master? Congratulations! That's an impressive rank.",
    (2,19,24): "Welcome, Taiki. If you have time, please keep granting wishes through quests. How far have you climbed at the colosseum? Platinum Master?! Even higher than Gold?",
    (2,19,25): "I've heard about your colosseum victories. Legend Master already?! Isn't that too fast for someone so young? Still, congratulations! Fight me someday too!",
    (2,19,26): "Taiki, this is the Service Counter. Bring me a ticket whenever you want to summon a Digimon!",
    (2,19,27): "You can change the nicknames given to your Digimon here.",
    (2,19,28): "Let's hurry to the DigiColosseum! It's packed with powerful opponents. I'm getting fired up!",
    (2,19,29): "Bronze Master? You did it, Taiki! It sounds shiny—like polished metal!",
    (2,19,30): "Silver Master? Great job, Taiki! It's gleaming so brightly!",
    (2,19,31): "Gold Master? Amazing, Taiki! It's sparkling so brightly I'm dizzy!",
    (2,19,32): "Platinum Master! Amazing! I don't even know what to say!",
    (2,19,33): "Legend Master?! What does that mean? A dense legend? What do we do now, Taiki?!",
    (2,19,34): "Taiki, are we going to the DigiColosseum? Pipismon wants to come too!",
    (2,19,35): "Congratulations on Bronze Master, Taiki! But keep going at the DigiColosseum. Pipismon wants to come!",
    (2,19,36): "Congratulations on Silver Master, Taiki! Keep going at the DigiColosseum. Pipismon wants to come!",
    (2,19,37): "Congratulations on Gold Master, Taiki! Keep going at the DigiColosseum. Pipismon wants to come!",
    (2,19,38): "Congratulations on Platinum Master, Taiki! Just a little farther at the DigiColosseum. Pipismon wants to come!",
    (2,19,39): "Congratulations on Legend Master, Taiki! Does that mean the DigiColosseum journey is over for Pipismon too?",
    (2,19,40): "You've decided to enter the DigiColosseum, right? Powerful teams from across the Digital World are waiting. Let's go, Taiki!",
    (2,19,41): "First, Bronze Master! Now let's move on. This is only the beginning for Taiki and Xros Heart!",
    (2,19,42): "Silver Master already?! Keep pushing!",
    (2,19,43): "Gold Master already?! We're getting close to the top!",
    (2,19,44): "Platinum Master?! You really did it, Taiki! The opponents above Gold aren't ordinary Digimon. This is getting exciting!",
    (2,19,45): "You've finally become Legend Master, Taiki! You're at the very top of DWM. What do we aim for now?",
    (2,19,46): "Thanks for coming! This is Penmon's West Knuckle City Item Shop—the Double Shop!",
    (2,19,47): "Taiki, this is the Service Counter. Bring me a ticket whenever you want to summon a Digimon!",
    (2,19,48): "Welcome back to West Knuckle City's Farm Shop! A good party begins with a good farm. That's the key, Bomber!",
    (2,19,49): "I heard you saved the El Est Zone from destruction. Thank you so much, Taiki!",
    (2,19,50): "You became Bronze Master? Well done! I only know the DigiColosseum through rumors, but your achievement deserves celebration. Congratulations, Taiki!",
    (2,19,51): "You became Silver Master? Congratulations! The Digital World's greatest fighters are beyond anything we can imagine.",
    (2,19,52): "You became Gold Master? Amazing! Gold sounds like the top—wait, Platinum is higher? There's always another level.",
    (2,19,53): "You finally became Platinum Master. Bronze, Silver, Gold, then Platinum, right? Even at that level, frightening things still exist. I suppose they always will.",
    (2,19,54): "Legend Master? Taiki has become a legend himself.",
    (2,19,55): "Thanks for coming! This is Penmon's East Knuckle City Item Shop—the E-Shop!",
    (2,19,56): "Taiki, this is the Service Counter. Bring me a ticket whenever you want to summon a Digimon!",
    (2,19,57): "Welcome back to East Knuckle City's Farm Shop! A good party begins with a good farm. That's the key, Bomber!",
    (2,19,58): "You saved the El Est Zone! El Est saved—E-Saved! No? Yeah, that slogan needs work.",
    (2,19,59): "You became Bronze Master? Great! It's fifth from the top? Then you're only getting started. Keep charging ahead!",
    (2,19,60): "You became Silver Master? I knew you could! Fourth from the top means there's still a way to go. Keep charging!",
    (2,19,61): "You became Gold Master? Gold, mithril—anything suits you! Next is Black Digizoid Master? No? Platinum? That's less dramatic.",
    (2,19,62): "You became Platinum Master? Incredible! That's second from the top, right? With only one legendary rank above, you're practically the best already!",
    (2,19,63): "You became Legend Master?! Congratulations, but isn't that the title ancient veterans earn? It's hard to believe someone so young holds it—even if you're strong.",
    (2,19,64): "Thanks for coming! This is Penmon's Spiral City Item Shop—the Spiral Shop!",
    (2,19,65): "Taiki, this is the Service Counter. Bring me a ticket whenever you want to summon a Digimon!",
    (2,19,66): "Welcome back to Spiral City's Farm Shop! A good party begins with a good farm. That's the key, Bomber!",
})

# Batch 3J: global prose records 3867-3928 (2,001 draft-English words).
OVERRIDES.update({
    (2,19,67): "I heard Taiki and the others fought ROG and became stars of Lost Space. What a dazzling group of heroes!",
    (2,19,68): "You became Bronze Master? Impressive! I made a bronze statue to celebrate, but when I placed it in Sky Fort, it fell over.",
    (2,19,69): "You became Silver Master? Congratulations! You're nearing the top. The hardest part may be almost over, but go all the way!",
    (2,19,70): "You became Gold Master? Excellent! You must be near the top—what, two ranks remain? Platinum and Legend? Still a long road.",
    (2,19,71): "You became Platinum Master? Congratulations! Only Legend remains. I heard its battles are absurdly difficult, even for Digimon.",
    (2,19,72): "You became Legend Master at last! There's only one thing left: keep moving forward and create an even greater legend!",
    (2,19,73): "Thanks for coming! This is Penmon's Skull City Item Shop—the Skull Shop!",
    (2,19,74): "Taiki, this is the Service Counter. Bring me a ticket whenever you want to summon a Digimon!",
    (2,19,75): "Welcome back to Skull City's Farm Shop! A good party begins with a good farm. That's the key, Bomber!",
    (2,19,76): "You were the ones who saved the El Est Zone, right? You really did it. That's incredible.",
    (2,19,77): "You're already Bronze Master? I knew you were strong, but that's amazing. Keep aiming higher!",
    (2,19,78): "You became Silver Master so quickly? Gold comes next, right? The tournament is filled with incredible fighters.",
    (2,19,79): "You finally became Gold Master? Gold sounds like the top, but Platinum and Legend still remain. How far will you go?",
    (2,19,80): "You became Platinum Master? I couldn't attend the DigiColosseum, but I was cheering from here. Congratulations! I'm truly happy for you!",
    (2,19,81): "You became Legend Master? A legend isn't something that ends—it begins with the story you create from this point forward.",
    (2,19,82): "You protected this Zone's gateway? Taiki and the others were as incredible as I expected. Thank you—everyone is celebrating!",
    (2,19,83): "You became Bronze Master? Congratulations! Bronze is actually my favorite rank. Higher ranks may be grander, but Bronze has the freshest challenger spirit!",
    (2,19,84): "You became Silver Master? You're a veteran now. Many competitors never rise beyond Silver, but I'm sure you will.",
    (2,19,85): "You became Gold Master? Then I can relax. If you stay focused, Platinum and Legend are within reach.",
    (2,19,86): "You became Platinum Master? Congratulations! You're among the Digital World's elite. Legend is another matter, but you're already this Zone's greatest fighter.",
    (2,19,87): "You became Legend Master? Congratulations! They say half of legendary teams eventually split up, but Xros Heart will be fine... right?",
    (2,19,88): "Thanks for coming! This is Penmon's Cloud City Item Shop—the Cloud Shop!",
    (2,19,89): "Taiki, this is the Service Counter. Bring me a ticket whenever you want to summon a Digimon!",
    (2,19,90): "Welcome back to Cloud City's Farm Shop! A good party begins with a good farm. That's the key, Bomber!",
    (2,19,91): "Xros Heart, saviors of the El Est Zone! Taiki, we're truly grateful!",
    (2,19,92): "Bronze Master? You did it! The DigiColosseum sounds amazing. I'd love to see it!",
    (2,19,93): "Silver Master already? I'm jealous! The world-class tournament must be heating up. What, it's not worldwide? Details!",
    (2,19,94): "Gold Master? That's incredible! Does that mean you can turn anything into gold now?",
    (2,19,95): "Platinum Master? Amazing, though platinum doesn't sound very exciting to me. They should give the rank a clearer name!",
    (2,19,96): "Legend Master?! You finally reached it. From the bottom of my heart, congratulations! Whatever anyone says, you're legends now!",
    (2,19,97): "You drove off ROG, Pino? Now you're entering the DWM Tournament? It's like a movie—Pino is becoming a superhero!",
    (2,19,98): "You became Bronze Master, Pino? Amazing! Your team is Xros Heart, right? Not Dark Heart—that was an El Est joke, Pino!",
    (2,19,99): "You became Silver Master, Pino? Congratulations! Fighting someone similar to you can be both easy and difficult. They were probably thinking the same thing, Pino!",
    (2,19,100): "You became Gold Master, Pino? Incredible! Fighting someone like yourself is complicated, but your opponent probably felt the same, Pino!",
    (2,19,101): "You became Platinum Master, Pino? Against the Bandits?! I heard they tried to shoot you! I'm relieved you're safe, Pino.",
    (2,19,102): "You became Legend Master, Pino? That's incredible, but are you satisfied? Becoming a legend is only the beginning of your story, Pino!",
    (2,19,103): "Thanks for coming! This is Penmon's Papyrus City Item Shop—the Papyrus Shop!",
    (2,19,104): "Taiki, this is the Service Counter. Bring me a ticket whenever you want to summon a Digimon!",
    (2,19,105): "Welcome back to Papyrus City's Farm Shop! A good party begins with a good farm. That's the key, Bomber!",
    (2,19,106): "ROG is gone and the Zone is ours again. It's all thanks to you. From the bottom of my heart, congratulations!",
    (2,19,107): "Bronze Master? Of course I know what bronze means. It's... something used for bells, right? Anyway, good luck!",
    (2,19,108): "Silver Master? Of course I know silver. It makes food taste better... maybe? Anyway, good luck!",
    (2,19,109): "G-Gold Master? I know gold! It's in... Golden Ruler? Never mind. Good luck!",
    (2,19,110): "Platinum Master? Of course I know what that is, but I'm busy right now. We'll discuss it later!",
    (2,19,111): "Legend Master? I don't understand complicated ranks. It means you're the strongest team at the DigiColosseum, right? That's incredible. You worked hard!",
    (2,19,112): "I'll remove the troublesome Digimon! Piko... piko! The nuisance is gone! A new quest has been posted to the Quest Monitor!",
    (2,19,113): "A new quest has been posted to the Quest Monitor!",
    (2,19,114): "Thanks for coming! This is Penmon's Earth Fort Item Shop—the Earth Shop! We carry plenty of useful items!",
    (2,19,115): "I'll remove the troublesome Digimon! Piko... piko! The nuisance is gone! A new quest has been posted to the Quest Monitor!",
    (2,19,116): "A new quest has been posted to the Quest Monitor!",
    (2,19,117): "I'll remove the troublesome Digimon! Piko... piko! The nuisance is gone! A new quest has been posted to the Quest Monitor!",
    (2,19,118): "A new quest has been posted to the Quest Monitor!",
    (2,19,119): "I'll remove the troublesome Digimon! Piko... piko! The nuisance is gone! A new quest has been posted to the Quest Monitor!",
    (2,19,120): "A new quest has been posted to the Quest Monitor!",
    (2,19,121): "I've heard rumors about you: a human who crossed Zones to help an amnesiac Weapon Digimon. You have the power to help Digimon grow. Your team will surely conquer this tournament.",
    (2,19,122): "You're Bronze Master? Impressive, as expected. But the real challenge begins now. Don't give up.",
    (2,19,123): "You're Silver Master? Impressive, but not surprising. Anyone can reach Silver with enough effort. From here, you'll discover the limits of your true strength.",
    (2,19,124): "You're Gold Master? Your strength is real. That title can only be grasped through accumulated battles and bonds.",
    (2,19,125): "You're Platinum Master? That genuinely surprises me. Only exceptional people reach that rank—and now you're one of them.",
    (2,19,126): "Ha-ha! So you've appeared, fool! Prepare for the brutal DWM Tournament! Sorry, I'm throwing a tantrum. Someone has to greet first-time visitors. What do you need?",
    (2,19,127): "You're Bronze Master. I watched the match—it was impressive. Plenty of challenges remain, but at least you weren't stumbling around blindly. Keep improving.",
    (2,19,128): "Silver Master! I watched that match too. You had to work harder this time, which made the victory even sweeter. That's how it should be!",
})

# Batch 3K: global prose records 3929-3972 (2,026 draft-English words).
OVERRIDES.update({
    (2,19,129): "You did it, Gold Master! I watched the match. You were in a tight spot, but that's not bad—victory feels better when you refuse to give up.",
    (2,19,130): "Platinum Master? Incredible! I watched you blow away the Bandits. They were fools, but don't underestimate them. That victory deserves respect!",
    (2,19,131): "So you're the hero who saved the Digital World? You don't look like it—but most heroes don't. If you're entering DWM, I'll be watching.",
    (2,19,132): "Bronze Master? Congratulations! I said I'd watch but missed the match. Sorry—I get distracted. I'll catch the next one!",
    (2,19,133): "Silver Master? Congratulations! I watched properly this time. It was impressive, though you escaped a real pinch. Stronger enemies await, and I'll be watching!",
    (2,19,134): "Gold Master! That was cool. The match ended so quickly I barely remember the opposing team, but a win is a win!",
    (2,19,135): "Congratulations, Platinum Master! I watched, and your team's strength is genuine. At this pace, you may reach the top!",
    (2,19,136): "You became Legend Master. I'm delighted, but now I can't watch you compete here anymore. Perhaps someday you'll return as a Battle Master. Thank you, Taiki the Legend Master.",
    (2,19,137): "Legend Master? I'm out of words. Are you retiring already? That rank feels like a certificate of completion. Congratulations, and excellent work!",
    (2,19,138): "Congratulations, Legend Master! Watching your team was always exciting. It's sad that you can't enter again, but thank you for every great battle!",
    (2,19,139): "First time entering DWM? I don't know who you are, but you'll be fine. Stop thinking and hit them with everything!",
    (2,19,140): "Bronze Master already? That was too easy. I'm not jealous!",
    (2,19,141): "Silver Master? DWM can't be that easy... can it?",
    (2,19,142): "Gold Master? I can't call it luck anymore. The hero you defeated once saved a Digital World. Maybe you're becoming a hero just like them.",
    (2,19,143): "Platinum Master already? Watching you charge straight ahead makes me regret every time I hesitated. You're annoyingly impressive.",
    (2,19,144): "Legend Master? Impossible! How can someone who still hangs around the music room be a living legend? Why am I getting so angry?",
    (2,19,145): "New face—is this your first DigiColosseum visit? Whose fan are you? I'm Sayo's biggest fan. Insult me if you like, but never insult Sayo!",
    (2,19,146): "I didn't realize you were the new challenger. Even as a veteran spectator, your casual appearance fooled me—and now you're Bronze Master! You may grow quickly. Welcome, from a Sayo fan!",
    (2,19,147): "Silver Master already? That was a fine battle. But now you'll face Sayo. I won't complain about fair competition, but don't you dare hurt her!",
    (2,19,148): "Gold Master? Congratulations. I never expected Sayo to lose so decisively, but it was a good fight. Even a devoted fan must admit that.",
    (2,19,149): "Congratulations, Platinum Master. Why the surprise? Yes, I'm a wild Sayo fan, but I'm a tournament spectator first. A great battle deserves honest praise.",
    (2,19,150): "Legend Master already? Forget the details—you worked incredibly hard! Congratulations, Sayo! Sorry—Taiki. My mouth acts on its own.",
    (2,19,151): "Hello, Taiki! Welcome to the DigiColosseum! I'm Justimon, Digimon of Justice—and as you can see, a tournament spectator of justice! Ha-ha-ha!",
    (2,19,152): "Taiki, you became Bronze Master! I knew you could. I always support the side of justice. If both sides are just, I support whichever shines brighter!",
    (2,19,153): "Taiki, Silver Master! Silver is the color of justice—and most of my body. I am Justimon, the Silver Digimon of Justice! Ha-ha-ha!",
    (2,19,154): "Taiki, Gold Master at last! Even after years watching tournaments, Xros Heart's brilliant battles astonish me. Everyone here is watching you closely!",
    (2,19,155): "Taiki, Platinum Master! Your true strength is astonishing. You may reach the very top! I once competed here too, though in a different kind of tournament. Ha-ha-ha!",
    (2,19,156): "Taiki, Legend Master at last! Congratulations! Legend is DWM's final rank, but not the end of your fight. Your journey to protect the Digital World's happiness has only begun!",
    (2,19,157): "Hero of the El Est Zone! We met before—though you may not remember. I never expected you to enter DWM. I'll cheer you on. Good luck!",
    (2,19,158): "Bronze Master? Amazing! I'll call you The Bronze Master—no? How about Number Five Rank? Why are you looking at me like that?",
    (2,19,159): "Silver Master! Amazing! Shall I call you The Silver Master? No? La Silver Master? Silver-Master? Titles are complicated!",
    (2,19,160): "Taichi the Gold Master! Wait, your name is Taiki? I said Taiki, didn't I? Sorry—really!",
    (2,19,161): "Taiki the Platinum Master! Did I say that right? No? Can I try again? Better leave it alone? Sorry.",
    (2,19,162): "You're Legend Master already? Watching your journey felt like a wonderful dream. On behalf of the El Est Zone, congratulations, Taiki Kudo—and thank you for everything.",
    (2,19,163): "Find the flying Digimon! Leader Hououmon is at Canyon Yard. If you get lost, check Quest Information on the Xros Loader. Good luck!",
    (2,19,164): "Find Hououmon, leader of the flying Digimon! Hououmon is currently at Canyon Yard.",
    (2,19,165): "Thanks, Taiki! Now you can use the airport!",
    (2,19,166): "With the Sky Passport I gave you, Hououmon can visit unlocked airports. Find keys in treasure chests to open more gates. First, speak to Hououmon at the Skyport by the Command Room!",
    (2,19,167): "Gathering the flying Digimon again sounds impossible? There are 99, and Hououmon seems to work alone. But you only need to recruit the other 98! Tell Biyomon, \"Leave it to me!\"",
    (2,19,168): "Tell Biyomon you'll gather all their friends!",
    (2,19,169): "Find the flying Digimon! Leader Parrotmon is at Grass Yard. If you get lost, check Quest Information on the Xros Loader. Good luck!",
    (2,19,170): "Find Parrotmon, leader of the flying Digimon! Parrotmon is currently at Grass Yard.",
    (2,19,171): "Thanks, Taiki! Now you can use the airport!",
    (2,19,172): "With the Sky Passport I gave you, Parrotmon can visit unlocked airports. Find keys in treasure chests to open more gates. First, speak to Parrotmon at the Skyport by the Command Room!",
})

# Batch 3L: global prose records 3973-4051 (2,038 draft-English words).
OVERRIDES.update({
    (2,19,173): "Gathering the flying Digimon again sounds impossible? There are 99, and Parrotmon seems to work alone. But you only need to recruit the other 98! Tell Biyomon, \"Leave it to me!\"",
    (2,19,174): "Tell Biyomon you'll gather all their friends!",
    (2,19,175): "I've always wanted to shed my prickly self and become smooth! Zudomon has an amazing shaver. Please bring it to me!",
    (2,19,176): "Bring Togemon the amazing shaver from Zudomon at West Knuckle Coast!",
    (2,19,177): "Thank you! Please accept this reward. One question: did Zudomon say anything about the shaver? I don't have to return it? I knew it...",
    (2,19,178): "I heard a frightening rumor about a red, slimy monster screaming along Knuckle Coast. Never mind. Thank you—I'll store this shaver for now.",
    (2,19,179): "Togemon wants my shaver? She can have it. But if she actually becomes smooth... never mind. Take it, and don't bring it back.",
    (2,19,180): "Tell Togemon everything. Good luck!",
    (2,19,181): "I've always wanted to shed my prickly self and become smooth! Drimogemon became smooth with an amazing shaver. Please bring it!",
    (2,19,182): "Bring Togemon the amazing shaver from Drimogemon at West Knuckle Coast!",
    (2,19,183): "Thank you! Please accept this reward. Did Drimogemon say anything about the shaver? I don't have to return it? I knew it...",
    (2,19,184): "I heard a frightening rumor about a red, slimy monster screaming along Knuckle Coast. Never mind. Thank you—I'll store this shaver for now.",
    (2,19,185): "Togemon wants my shaver? She can have it. But if she actually becomes smooth... never mind. Take it, and don't bring it back.",
    (2,19,186): "Tell Togemon everything. Good luck!",
    (2,19,187): "My Giro-Giro Gang challenged our eternal rivals, the Mame-Mame Gang, to an all-out battle! Now I'm wondering what to do.",
    (2,19,188): "Ask Nanomon L and TD Ballmon of the Giro-Giro Gang where the Mame-Mame Gang is!",
    (2,19,189): "Thanks, Taiki! The Mame-Mame Gang is finished. But the Giro-Giro Gang caused trouble too, so we're disbanding!",
    (2,19,190): "The Giro-Giro Gang is dissolved! Good work.",
    (2,19,191): "Mametyramon of the Mame-Mame Gang is my eternal rival. Who else could lead them against us? Obviously me—wait!",
    (2,19,192): "Where's the Mame-Mame Gang? TD Ballmon might know. He's always nearby, soaking wet and covered in salt.",
    (2,19,193): "MetalMamemon of the Mame-Mame Gang is my eternal rival. Giromon claimed he led our battle, but actually it was me!",
    (2,19,194): "I don't know where the Mame-Mame Gang is, but they're probably nearby. They always seem to be wherever I go.",
    (2,19,195): "You're working for the Giro-Giro Gang?! Enough talk—fight!",
    (2,19,196): "Giromon sent you? That's ridiculous! The Mame-Mame Gang disbanded ages ago.",
    (2,19,197): "Leave Giromon alone. I'm done dealing with you. Now I'm getting serious.",
    (2,19,198): "My Mame-Mame Gang challenged our eternal rivals, the Giro-Giro Gang, to an all-out battle! Now I'm wondering what to do.",
    (2,19,199): "Ask Mametyramon and MetalMamemon of the Mame-Mame Gang where the Giro-Giro Gang is!",
    (2,20,0): "Thanks, Taiki! The Giro-Giro Gang is finished. But the Mame-Mame Gang caused trouble too, so we're disbanding. Accept this final gift!",
    (2,20,1): "The Mame-Mame Gang is dissolved! Good work.",
    (2,20,2): "Nanomon L of the Giro-Giro Gang is my eternal rival. Who else could lead us against them? Obviously me—wait!",
    (2,20,3): "Where's the Giro-Giro Gang? MetalMamemon might know. He's always nearby, glaring.",
    (2,20,4): "TD Ballmon of the Giro-Giro Gang is my eternal rival. Mamemon claimed he led our battle, but actually it was me!",
    (2,20,5): "I don't know where the Giro-Giro Gang is, but they're probably nearby. They always seem to be wherever I go.",
    (2,20,6): "You're working for the Mame-Mame Gang?! Enough talk—fight!",
    (2,20,7): "Mamemon sent you? That's ridiculous! The Giro-Giro Gang disbanded ages ago.",
    (2,20,8): "Leave Mamemon alone. I'm done dealing with you. Now I'm getting serious.",
    (2,20,9): "I heard my impostor appears at East Knuckle Coast. Find that fake for me! Good luck!",
    (2,20,10): "Find my impostor at East Knuckle Coast. When you do, give him a good punch!",
    (2,20,11): "You fought Monzaemon? Where is he? Oh, he lost weight? Sorry—apparently he wasn't my impostor.",
    (2,20,12): "I wish that fake would stop. Wait, Monzaemon? That's awful... See you!",
    (2,20,13): "Yukidarumon? What about him? He called me his impostor?! I'll make him regret that!",
    (2,20,14): "That's enough for today. Tell that fool Yukidarumon to lose some weight!",
    (2,20,15): "Yukidarumon's supposed impostor is just a similar silhouette. Tell him to lose weight. See you!",
    (2,20,16): "I heard my impostor appears at East Knuckle Coast. Find that fake for me! Good luck!",
    (2,20,17): "Find my impostor at East Knuckle Coast. When you do, give him a good punch!",
    (2,20,18): "You fought Pandamon? Where is he? Oh, he lost weight? Sorry—apparently he wasn't my impostor.",
    (2,20,19): "I wish that fake would stop. Wait, Pandamon? That's awful... See you!",
    (2,20,20): "Yukidarumon? He called me his impostor?! What nonsense!",
    (2,20,21): "Yukidarumon and I only have similar silhouettes. Our colors are completely different. Tell that fool to lose weight!",
    (2,20,22): "That's enough for today. Tell Yukidarumon to lose weight!",
    (2,20,23): "Wisemon keeps interfering with my studies! He's in western Spiral Amazon. Do something!",
    (2,20,24): "Defeat Wisemon in western Spiral Amazon! If he keeps interfering, I'll never return to Witchelny's school!",
    (2,20,25): "Thank you! Now I can finally focus on school. But I forgot all my fire magic and can't relearn it. Maybe I'm finished. I can't return to Witchelny.",
    (2,20,26): "Will you recruit me? I'll leave Witchelny behind and live in this Zone. I'll wait here, so talk to me anytime.",
    (2,20,27): "Wizardmon says I'm interfering with his studies? He never studies! That fool is searching for an excuse to quit. Don't blame me!",
    (2,20,28): "Tell Wizardmon to stop making excuses and study hard.",
    (2,20,29): "Tell Wizardmon to keep training. He's one of Witchelny's elite; he shouldn't waste his talent here.",
    (2,20,30): "Diatrymon keeps harassing me. I'm sure he plans to catch and eat me! He's in western Spiral Amazon—do something!",
    (2,20,31): "Defeat Diatrymon in western Spiral Amazon! At this rate he'll devour me!",
    (2,20,32): "Thank you! Honey? Powder? None of that matters now. I finally understand: I can defeat any Digimon if I try! No more hiding behind protection.",
    (2,20,33): "Will you recruit me? I want to develop the strength I've never used. I'll wait here, so call me anytime!",
    (2,20,34): "Mashmon sent you? I'm not listening. Come closer and I'll blast you away! Both of you are fools!",
    (2,20,35): "Mashmon says I'll eat him? He's the poisonous mushroom spreading moldy spores! If he's angry, tell him to stop spraying powder everywhere!",
    (2,20,36): "If you're helping, take all this moldy powder back to Mashmon!",
    (2,20,37): "D-danger, Devi! I owe BEelzemon 200,000 bits! Please fool him with this fake bit-like object. He's at the skull-shaped building, Devi!",
    (2,20,38): "I owe BEelzemon 200,000 bits. Please fool him with this bit-like object. He's at the skull-shaped building, Devi!",
    (2,20,39): "You delivered it! Looks like I escaped paying at the last second, Devi!",
    (2,20,40): "Somehow everything worked out, Devi! He may demand payment again later... Huh? I don't need the fake bit back.",
    (2,20,41): "You're Devimon's substitute? Fine. Hand over 200,000 bits. What's this ugly white thing—\"bit-like\"? It's obviously fake! Pay or I'll tear the money from you!",
    (2,20,42): "I don't care who you are or why you're here. Give me 200,000 bits now!",
    (2,20,43): "Pay 200,000 bits?", (2,20,44): "Yes, pay.",
    (2,20,45): "No way!", (2,20,46): "Then hand over 200,000 bits!",
    (2,20,47): "Hmph. You defeated me, so you've proven power worth 200,000 bits. Tell Devimon I'll forgive him this time. And keep that fake bit!",
    (2,20,48): "Hmph. That's exactly 200,000 bits. Tell Devimon to bring it himself next time.",
    (2,20,49): "I said 200,000 bits. Can't you count?",
    (2,20,50): "Silence, Devimon's errand boy. There's nothing you can do now.",
    (2,20,51): "Money is evil—small evil! I owe BEelzemon bits, so please fool him with this bit-like object. He's at the skull-shaped building!",
})

# Batch 3M: global prose records 4052-4122 (2,009 draft-English words).
OVERRIDES.update({
    (2,20,52): "I owe Beelzemon 200,000 bits. Please fool him with this bit-like object. He's at the skull-shaped building!",
    (2,20,53): "You delivered it! You saved my life, Evil! Please accept this little reward!",
    (2,20,54): "Somehow everything worked out, Evil! He may demand payment again later... Huh? I don't need the fake bit back.",
    (2,20,55): "You're Evilmon's substitute? Fine. Hand over 200,000 bits. What's this ugly white \"bit-like\" object? It's obviously fake! Pay or I'll tear the money from you!",
    (2,20,56): "I don't care who you are or why you're here. Give me 200,000 bits now!",
    (2,20,57): "Then hand over 200,000 bits!",
    (2,20,58): "Hmph. You defeated me, so you've proven power worth 200,000 bits. Tell Evilmon I'll forgive him this time. And keep that fake bit!",
    (2,20,59): "Hmph. That's exactly 200,000 bits. Tell Evilmon to bring it himself next time.",
    (2,20,60): "I said 200,000 bits. Can't you count?", (2,20,61): "Silence, Evilmon's errand boy. There's nothing you can do now.",
    (2,20,62): "Pinocchimon has searched for this object for ages. Find it, have Vademon verify it, then deliver the real one to Pinocchimon. Hurry!",
    (2,20,63): "It fell in West Skull Glacier. Once found, ask Vademon in East Spiral Amazon to authenticate it. If genuine, deliver it to Pinocchimon in the Dark Tunnel.",
    (2,20,64): "You found and delivered it already? Was he happy? Good. He wanted it desperately, but was too embarrassed to search himself. Thank you.",
    (2,20,65): "One more request: if possible, let me join your team.", (2,20,66): "Welcome back!",
    (2,20,67): "Let me inspect it... This looks convincing but isn't genuine. Frankly, it's squid droppings. Please take it away.",
    (2,20,68): "Let me inspect it... This is genuine! It's exactly what Pinocchimon sought. Hurry and deliver it!",
    (2,20,69): "It's called a Wish Star. They say a sincere wish made upon it will come true. Deliver it to Pinocchimon in the Dark Tunnel.",
    (2,20,70): "This is the Wish Star? I can have it? Thank you! I'll wish for Lilamon to become honest so we can be friends.",
    (2,20,71): "Thanks, Taiki. One more favor: could you check whether Lilamon has become more honest?",
    (2,20,72): "ToyAgumon has searched for a certain object for ages. Find it, have Vademon authenticate it, then deliver the real one to ToyAgumon.",
    (2,20,73): "It fell in West Skull Glacier. Ask Vademon in East Spiral Amazon to authenticate it, then deliver it to ToyAgumon in the Dark Tunnel.",
    (2,20,74): "You delivered it? Was he happy? Good. I meant to go myself, but flying always causes trouble. I'm relieved. Thank you!",
    (2,20,75): "One more request: if possible, let me join your team. Call me whenever you're ready.", (2,20,76): "Welcome back!",
    (2,20,77): "Let me inspect it... This looks convincing but isn't genuine. Frankly, it's squid droppings. Please take it away.",
    (2,20,78): "Let me inspect it... This is genuine! It's exactly what ToyAgumon sought. Hurry and deliver it!",
    (2,20,79): "It's called a Wish Star. They say a sincere wish made upon it will come true. Deliver it to ToyAgumon in the Dark Tunnel.",
    (2,20,80): "This is the Wish Star? Thank you! I'll wish for Parrotmon to recover and fly freely again!",
    (2,20,81): "Thanks, Taiki. One more favor: could you check on Parrotmon for me?",
    (2,20,82): "You've built quite a reputation. To test you, I've assembled an elite team called the Skill Testers! Never mind the name—interested?",
    (2,20,83): "Find the Skill Testers in West Cloud Ruins. Defeat them and return to me. Good luck!",
    (2,20,84): "Excellent work! Here's your reward.",
    (2,20,85): "Would you recruit someone who recognizes your skill? Call me anytime.",
    (2,20,86): "You're here for the skill test? Hold still while I evaluate you... All right. These are your opponents! Ready... Bomber!",
    (2,20,87): "Your skill is impressive. Keep training and you'll improve even more. Return to Kabukimon for your reward!",
    (2,20,88): "You're still inexperienced. One careless moment could defeat you. Come back when you've improved.",
    (2,20,89): "You've built quite a reputation. To test you, I've assembled an elite team called the Skill Testers! Yes, the name stays. Interested?",
    (2,20,90): "Find the Skill Testers in West Cloud Ruins.", (2,20,91): "Excellent work! Here's your reward.",
    (2,20,92): "Would you recruit someone who recognizes your hidden talent? Call me anytime.",
    (2,20,93): "You're here for the skill test? Hold still while I evaluate you... All right. These are your opponents! Ready... Bomber!",
    (2,20,94): "Your skill is impressive. Keep training and you'll improve even more. Return to Knightmon for your reward!",
    (2,20,95): "You're still inexperienced. One careless moment could defeat you. Come back when you've improved.",
    (2,20,96): "Snimon at the DigiFarm asked me to interview Dinobeemon in West Spiral Amazon and record it on this voice recorder. Make sure it's Dinobeemon!",
    (2,20,97): "Interview Dinobeemon in West Spiral Amazon and record it with this voice recorder.",
    (2,20,98): "Thanks! Let me hear it... Wait, why does this interview have echoing background music?",
    (2,20,99): "If possible, let me join your team too. Call me if you're interested.",
    (2,20,100): "An interview? Sure! You're using a voice recorder? I expected this, so I've already recorded D voice data.",
    (2,20,101): "To all my fans—thanks for your support! Yeah, check it out!",
    (2,20,102): "An interview? Who do you think I am? Dinobeemon?! I'll blast this little fool away!",
    (2,20,103): "Are your eyes or brain rotten? A bug and a dragon are completely different!",
    (2,20,104): "That must be Dinobeemon. Stop wasting time here and go!",
    (2,20,105): "Ankylomon at the DigiFarm asked me to interview Paildramon in West Spiral Amazon and record it. Make sure it's Paildramon!",
    (2,20,106): "Interview Paildramon in West Spiral Amazon and record it with this voice recorder. You know who Paildramon is, right?",
    (2,20,107): "Thanks! Let me hear it... Wait, is this really an interview? It sounds like nonstop screaming.",
    (2,20,108): "If possible, let me join your team too. Call me if you're interested.",
    (2,20,109): "An interview? Fine! I expected this, so I've already recorded P voice data.",
    (2,20,110): "Please send my best to all the fans! Good luck!",
    (2,20,111): "You want to interview me, Dino...? Who am I? Paildramon, Paildramon, and also Paildramon! Fine, anyone can make a mistake—but that was inexcusable!",
    (2,20,112): "Your eyes, brain, and judgment are all terrible! How can you mistake a dragon for a bug?",
    (2,20,113): "The one you're looking for is Paildramon. Stop sulking and go!",
    (2,20,114): "I have a difficult mission! Find Piedmon and answer every quiz correctly. Failure could end badly. Start at Knuckle Coast!",
    (2,20,115): "Find Piedmon and answer his quiz. Finding him is the first step!",
    (2,20,116): "You finished already? Amazing! I wasn't sure anyone could survive Piedmon's entire quiz—but perhaps only you could.",
    (2,20,117): "By the way, would you recruit me? Call me anytime.",
    (2,20,118): "You found the great Piedmon! Special Digimon Quiz, Part One: What is Whamon's signature move?",
    (2,20,119): "Tidal Wave", (2,20,120): "Dawdle Week", (2,20,121): "Try Again!",
    (2,20,122): "Correct! Tidal Wave! With a body that huge, the answer is obvious!",
})

# Batch 3N: Piedmon's quiz chain, rumor quests, and the TeriLop fan quest.
_PIEDMON_WRONG = (
    "Noooo! Wrong answer! That's a 3,000-bit fine! "
    "What, you thought I was joking? Nope! I'm taking it straight from your wallet! Ha haaa!"
)
_PIEDMON_BROKE = (
    "Huh? I was really going to take it, but you don't have enough money! "
    "You slipped out of that one nicely, huh? Ha haaa!"
)
_PIEDMON_NEXT_2 = (
    "Next comes Question Two! Think you can get it right? "
    "I'll be waiting in Flower Prairie! Ha haaa!"
)
_PIEDMON_FIND_2 = "Find me next in Flower Prairie! Ha haaa!"
_PIEDMON_NEXT_3 = (
    "Next comes Question Three! Think you can get it right? "
    "I'll be waiting in East Digital Space! Ha haaa!"
)
_PIEDMON_FIND_3 = "Find me next in East Digital Space! Ha haaa!"
_PIEDMON_NEXT_4 = (
    "Next comes Question Four! Think you can get it right? "
    "I'll be waiting in North Papyrus Desert! Ha haaa!"
)
_PIEDMON_FIND_4 = "Find me next in North Papyrus Desert! Ha haaa!"
_TERILOP_REQUEST = (
    "TeriLop just released a new CD! Could you ask their manager, LadyDevimon, "
    "to get me an autographed copy? She's in West Spiderweb Ruins right now!"
)
_TERILOP_REMINDER = (
    "Ask TeriLop's manager, LadyDevimon, for an autographed TeriLop CD. "
    "She's in West Spiderweb Ruins right now!"
)
_TERILOP_REWARD = (
    "...I'm so moved! I might start singing before I even put it in the player! "
    "Thank you so much. Please take this reward!"
)
_TERILOP_HUM = (
    "...Huh? Oh, sorry! I got a little carried away. "
    "Hmm-hm, hm-hmm, hmm-hmm-hmmm! Teri-lori-lop, TeriLop!"
)
_MISSING_PLANNER = (
    "Another autograph? This is no time for that! I lost the system planner "
    "with TeriLop's entire schedule! I can't even contact them without it. "
    "Please hurry and find it!"
)
_PLANNER_LOCATION = (
    "I noticed my system planner was gone after visiting South Papyrus Desert. "
    "I must have dropped it there. Please search the area!"
)
_PLANNER_RETURN = (
    "Oh, thank you! Now I can find TeriLop... Let's see... They're appearing in "
    "East Skull Glacier right now! I'll tell them you're coming, so get the autograph directly!"
)
_TERILOP_LOCATION = (
    "TeriLop is in East Skull Glacier right now. I'll tell them you're coming, "
    "so get the autograph directly!"
)
_TERILOP_FAN = (
    "Oh, are you one of our fans? Our manager said you were coming, so we signed the CD. "
    "Have we met before? No, right? Don't tell us you've followed us since before we were famous, "
    "or post embarrassing debut photos online! Ah ha ha... Anyway, here's the CD!"
)
_TERILOP_SIGNOFF_A = (
    "Keep supporting TeriLop! Teri-lori-lop! ...Tch. Huh? Did I say something weird? No, right?"
)
_TERILOP_GREETING = (
    "Oh, we heard about you! You're a fan, right? Thanks for always supporting us! "
    "LadyDevimon explained everything. Give them the CD and get them out... of here, okay? "
    "S-sorry! I'm exhausted, and my tact filter just completely fell out!"
)
OVERRIDES.update({
    (2,20,123): _PIEDMON_WRONG,
    (2,20,124): _PIEDMON_BROKE,
    (2,20,125): _PIEDMON_NEXT_2,
    (2,20,126): _PIEDMON_FIND_2,
    (2,20,127): (
        "You found the great Piedmon again! Special Digimon Quiz, Part Two: "
        "What is Mamemon's signature move?"
    ),
    (2,20,128): "Smiley Bomb",
    (2,20,129): "Spicy Bomb",
    (2,20,130): (
        "Yeees! Smiley Bomb is correct! Of course, one hit leaves you unconscious, "
        "not smiling! Ha haaa!"
    ),
    (2,20,131): _PIEDMON_WRONG,
    (2,20,132): _PIEDMON_BROKE,
    (2,20,133): _PIEDMON_NEXT_3,
    (2,20,134): _PIEDMON_FIND_3,
    (2,20,135): (
        "You found the great Piedmon yet again! Special Digimon Quiz, Part Three: "
        "What is Monzaemon's signature move?"
    ),
    (2,20,136): "Lovely Attack",
    (2,20,137): "Lovely Couple",
    (2,20,138): (
        "Yeees! Lovely Attack is correct! But when that move hits, you don't feel love. "
        "You feel hate... or maybe death! Ha haaa!"
    ),
    (2,20,139): _PIEDMON_WRONG,
    (2,20,140): _PIEDMON_BROKE,
    (2,20,141): _PIEDMON_NEXT_4,
    (2,20,142): _PIEDMON_FIND_4,
    (2,20,143): (
        "You stubbornly found the great Piedmon again! Special Digimon Quiz, Part Four: "
        "What is Octomon's signature move?"
    ),
    (2,20,144): "Spurting Ink",
    (2,20,145): "Sporting Rink",
    (2,20,146): (
        "Yeees! Spurting Ink is correct! Getting hit by it is seriously disgusting "
        "and totally depressing! Ha haaa!"
    ),
    (2,20,147): _PIEDMON_WRONG,
    (2,20,148): _PIEDMON_BROKE,
    (2,20,149): (
        "Yay, congratulations! That wraps up my delightful quiz for our delightful winner! "
        "Report your results to Myotismon in Papyrus City, okay? Ha haaa!"
    ),
    (2,20,150): (
        "My delightful quiz is already over! Report your results to Myotismon in Papyrus City!"
    ),
    (2,20,151): (
        "I've got a truly brutal mission for you! Find Piedmon and answer every one of his quizzes. "
        "If you fail, something awful may happen! Start at Knuckle Coast!"
    ),
    (2,20,152): (
        "Find Piedmon and answer his quizzes! First you have to track him down. "
        "Everything starts there!"
    ),
    (2,20,153): (
        "What?! You finished already?! I'm amazed. I know I assigned the mission, "
        "but I never thought anyone could endure Piedmon's whole quiz. You may be the only one!"
    ),
    (2,20,154): (
        "Oh, one more thing... Want me on your team? If you're interested, just come talk to me!"
    ),
    (2,20,155): (
        "Yeees! Tidal Wave is correct! That's one massive tsunami - way too huge to laugh off! Ha haaa!"
    ),
    (2,20,156): _PIEDMON_WRONG,
    (2,20,157): _PIEDMON_BROKE,
    (2,20,158): _PIEDMON_NEXT_2,
    (2,20,159): _PIEDMON_FIND_2,
    (2,20,160): (
        "Yeees! Smiley Bomb is correct! Of course, one hit leaves you unconscious, "
        "not smiling! Ha haaa!"
    ),
    (2,20,161): _PIEDMON_WRONG,
    (2,20,162): _PIEDMON_BROKE,
    (2,20,163): _PIEDMON_NEXT_3,
    (2,20,164): _PIEDMON_FIND_3,
    (2,20,165): (
        "Yeees! Lovely Attack is correct! But when that move hits, love is the last thing you feel! Ha haaa!"
    ),
    (2,20,166): _PIEDMON_WRONG,
    (2,20,167): _PIEDMON_BROKE,
    (2,20,168): _PIEDMON_NEXT_4,
    (2,20,169): _PIEDMON_FIND_4,
    (2,20,170): (
        "Yeees! Spurting Ink is correct! Getting hit by it is seriously disgusting "
        "and totally depressing! Ha haaa!"
    ),
    (2,20,171): _PIEDMON_WRONG,
    (2,20,172): _PIEDMON_BROKE,
    (2,20,173): (
        "Yay, congratulations! That wraps up my delightful quiz for our delightful winner! "
        "Report your results to Okuwamon in Papyrus City, okay? Ha haaa!"
    ),
    (2,20,174): (
        "My delightful quiz is already over! Report your results to Okuwamon in Papyrus City!"
    ),
    (2,20,175): (
        "You have Buraimon on your DigiFarm, right? Someone's spreading nasty rumors about him. "
        "Find the culprit and teach them a lesson! Angewomon has information in East Skull Glacier."
    ),
    (2,20,176): (
        "Someone's spreading nasty rumors about Buraimon. Find the culprit and teach them a lesson!"
    ),
    (2,20,177): (
        "Buraimon's reputation is safe now. Thank you! Please accept this reward."
    ),
    (2,20,178): (
        "Would you consider adding me to your team? If you're interested, come talk to me."
    ),
    (2,20,179): (
        "I found the one spreading rumors about Buraimon: Sinduramon in Papyrus Desert! "
        "Hurry there and teach him a lesson!"
    ),
    (2,20,180): (
        "Sinduramon was spreading the rumors! Hurry to Papyrus Desert and teach him a lesson!"
    ),
    (2,20,181): (
        "Buraimon has athlete's foot! Buraimon has athlete's foot! It's contagious, so stay away! "
        "Run, hide, evacuate!"
    ),
    (2,20,182): (
        "...I-I'm sorry. I couldn't stand seeing everyone like Buraimon so much. "
        "I won't do it again. Please forgive me..."
    ),
    (2,20,183): (
        "I won't spread any more weird rumors. I'll apologize properly to Buraimon and ask him to forgive me..."
    ),
    (2,20,184): (
        "You have MagnaAngemon on your DigiFarm, right? Someone's spreading nasty rumors about him. "
        "Find the culprit and teach them a lesson! Angewomon has information in East Skull Glacier."
    ),
    (2,20,185): (
        "Someone's spreading nasty rumors about MagnaAngemon. Find the culprit and teach them a lesson!"
    ),
    (2,20,186): (
        "MagnaAngemon's reputation is safe now. Thank you! Please accept this reward."
    ),
    (2,20,187): (
        "Would you consider adding me to your team? If you're interested, come talk to me."
    ),
    (2,20,188): (
        "I found the one spreading rumors about MagnaAngemon: Sinduramon in Papyrus Desert! "
        "Hurry there and teach him a lesson!"
    ),
    (2,20,189): (
        "Sinduramon was spreading the rumors! Hurry to Papyrus Desert and teach him a lesson!"
    ),
    (2,20,190): (
        "MagnaAngemon has athlete's foot! MagnaAngemon has athlete's foot! "
        "It's contagious, so stay away! Run, hide, evacuate!"
    ),
    (2,20,191): (
        "...I-I'm sorry. I couldn't stand seeing everyone like MagnaAngemon so much. "
        "I won't do it again. Please forgive me..."
    ),
    (2,20,192): (
        "I won't spread any more weird rumors. I'll apologize properly to MagnaAngemon and ask him to forgive me..."
    ),
    (2,20,193): _TERILOP_REQUEST,
    (2,20,194): _TERILOP_REMINDER,
    (2,20,195): _TERILOP_REWARD,
    (2,20,196): _TERILOP_HUM,
    (2,20,197): _MISSING_PLANNER,
    (2,20,198): _PLANNER_LOCATION,
    (2,20,199): _PLANNER_RETURN,
    (2,21,0): _TERILOP_LOCATION,
    (2,21,1): _TERILOP_FAN,
    (2,21,2): _TERILOP_SIGNOFF_A,
    (2,21,3): _TERILOP_GREETING,
    (2,21,4): (
        "You've only seen us at our least glamorous, but please keep supporting TeriLop! "
        "Teri-lori-lop! ...Ha... ha ha..."
    ),
    (2,21,5): _TERILOP_REQUEST,
    (2,21,6): _TERILOP_REMINDER,
    (2,21,7): _TERILOP_REWARD,
    (2,21,8): _TERILOP_HUM,
    (2,21,9): _MISSING_PLANNER,
    (2,21,10): _PLANNER_LOCATION,
    (2,21,11): _PLANNER_RETURN,
    (2,21,12): _TERILOP_LOCATION,
    (2,21,13): _TERILOP_FAN,
    (2,21,14): _TERILOP_SIGNOFF_A,
    (2,21,15): _TERILOP_GREETING,
    (2,21,16): (
        "You've only seen our awkward side, but give us a little more time. "
        "We'll make our big break! Please keep supporting TeriLop! Teri-lori-lop! ...Ha... ha ha..."
    ),
    (2,21,17): (
        "Gah! I can't forgive MegaGargomon! That oversized jerk thinks he can do whatever he wants! "
        "We're rebuilding the disbanded Giro-Giro Gang, joining forces with the Mame-Mame Gang, "
        "and blasting him away! Lend us your strength! First, meet our crew at Crystal Volcano!"
    ),
})
del (
    _PIEDMON_WRONG, _PIEDMON_BROKE, _PIEDMON_NEXT_2, _PIEDMON_FIND_2,
    _PIEDMON_NEXT_3, _PIEDMON_FIND_3, _PIEDMON_NEXT_4, _PIEDMON_FIND_4,
    _TERILOP_REQUEST, _TERILOP_REMINDER, _TERILOP_REWARD, _TERILOP_HUM,
    _MISSING_PLANNER, _PLANNER_LOCATION, _PLANNER_RETURN, _TERILOP_LOCATION,
    _TERILOP_FAN, _TERILOP_SIGNOFF_A, _TERILOP_GREETING,
)

# Batch 3O: the rival-gang alliance, UDY trials, and recruitment quests.
_GANG_RENDEZVOUS = (
    "Everyone's already at Crystal Volcano! Taiki, join up with them as their bodyguard!"
)
_GANG_REWARD = (
    "Thanks, Taiki! Take this reward! The Mame-Mame Gang and Giro-Giro Gang fought forever, "
    "but we're really alike and only wanted to compete. Together, nothing can scare us!"
)
_GANG_RECRUIT = "Want me on your team? If you're interested, come talk to me anytime!"
_GANG_LOSS_1 = (
    "Ugh... I lost. I let my guard down! And don't ask whether I'd have won otherwise!"
)
_GANG_CHASE_1 = (
    "Darn that oversized MegaGargomon! He won't escape Crystal Volcano!"
)
_GANG_LOSS_2 = (
    "Ugh... I lost. I underestimated him! I don't want to hear what would've happened otherwise."
)
_GANG_CHASE_2 = (
    "Grrr! Darn you, MegaGargomon! We'll corner you at Crystal Volcano and finish this!"
)
_GANG_LOSS_3 = (
    "Ugh... I lost. I never expected that... Okay, fine. He really is as strong as they say."
)
_GANG_CHASE_3 = (
    "Aw, man... If MegaGargomon escapes Crystal Volcano, we'll never catch him..."
)
_GANG_LOSS_4 = (
    "Ugh... I lost, but I was so close! Not asking how close is the kind thing to do, okay?"
)
_GANG_CHASE_4 = (
    "Raaagh! MegaGargomon won't escape from Crystal Volcano!"
)
_GANG_LOSS_5 = (
    "Ugh... I lost. But he's finished! I chased him into Crystal Cave..."
)
_GANG_FINISH = (
    "Please... Go to Crystal Cave and finish off MegaGargomon!"
)
_MEGAGARGO_BOAST = (
    "You came to finish me off? The Mame-Mame and Giro-Giro Gangs sent you? "
    "They never landed one hit! How can you finish a fight they never started? "
    "You think I'd lose to those runts?!"
)
_MEGAGARGO_LOSS = (
    "Yeah, I lost. I'll admit that much. But I didn't lose to those runts, got it? "
    "Make sure you remember that!"
)
_MEGAGARGO_APOLOGY = (
    "I don't care who won between us. Stepping on those runts was just an accident. "
    "Tell them I'm sorry - they were too tiny to see!"
)
_UDY_OFFER = (
    "So you're proud of your skills? We formed a team of elite Digimon to test fighters like you! "
    "Brace yourself for the name: UDE-DAMESHI-YA, or UDY! Yes, I just made it up. "
    "Beat them and you'll earn a huge reward. Interested?"
)
_UDY_MISSION = (
    "Head to Tokona Sea and fight UDE-DAMESHI-YA, the UDY! Beat them, then return for your reward. Good luck!"
)
_UDY_REWARD = (
    "Good job! Here's your reward. UDY and I officially guarantee your skills!"
)
_UDY_FAREWELL = "See you around! Keep sharpening those skills!"
_UDY_FIGHT = (
    "UDE-DAMESHI-YA, shortened to UDY? Who came up with that name? ...Whatever. "
    "You're the hotshot looking for a skill test, right? I've already sized you up. "
    "Time to meet the fists your skills deserve! Ready... Bomber!"
)
_UDY_STAGE_2 = (
    "All right, you pass. Not bad! But that was only Stage One. Here comes Stage Two! Ready... Bomber!"
)
_UDY_STAGE_3 = (
    "Good, you pass! You've got real skill. But that was only Stage Two. Here comes Stage Three! Ready... Bomber!"
)
_UDY_COMPLETE = (
    "That's it - well done! Your confidence is justified. Go back and collect your reward!"
)
_UDY_ACRONYM = (
    "UDE means Unbelievable, Dangerous, Excellent! I just invented that, but carve it into your heart! Yeah... Bomber!"
)
OVERRIDES.update({
    (2,21,18): _GANG_RENDEZVOUS,
    (2,21,19): _GANG_REWARD,
    (2,21,20): _GANG_RECRUIT,
    (2,21,21): _GANG_LOSS_1,
    (2,21,22): _GANG_CHASE_1,
    (2,21,23): _GANG_LOSS_2,
    (2,21,24): _GANG_CHASE_2,
    (2,21,25): _GANG_LOSS_3,
    (2,21,26): _GANG_CHASE_3,
    (2,21,27): _GANG_LOSS_4,
    (2,21,28): _GANG_CHASE_4,
    (2,21,29): _GANG_LOSS_5,
    (2,21,30): _GANG_FINISH,
    (2,21,31): _MEGAGARGO_BOAST,
    (2,21,32): _MEGAGARGO_LOSS,
    (2,21,33): _MEGAGARGO_APOLOGY,
    (2,21,34): (
        "I can't forgive MegaGargomon! That oversized jerk thinks he can do whatever he wants! "
        "We're rebuilding the Mame-Mame Gang, joining forces with the Giro-Giro Gang, and blasting him away! "
        "Taiki, lend us your strength! Meet our crew at Crystal Volcano!"
    ),
    (2,21,35): _GANG_RENDEZVOUS,
    (2,21,36): _GANG_REWARD,
    (2,21,37): _GANG_RECRUIT,
    (2,21,38): _GANG_LOSS_1,
    (2,21,39): _GANG_CHASE_1,
    (2,21,40): _GANG_LOSS_2,
    (2,21,41): _GANG_CHASE_2,
    (2,21,42): _GANG_LOSS_3,
    (2,21,43): _GANG_CHASE_3,
    (2,21,44): _GANG_LOSS_4,
    (2,21,45): _GANG_CHASE_4,
    (2,21,46): _GANG_LOSS_5,
    (2,21,47): _GANG_FINISH,
    (2,21,48): _MEGAGARGO_BOAST,
    (2,21,49): _MEGAGARGO_LOSS,
    (2,21,50): _MEGAGARGO_APOLOGY,
    (2,21,51): _UDY_OFFER,
    (2,21,52): _UDY_MISSION,
    (2,21,53): _UDY_REWARD,
    (2,21,54): _UDY_FAREWELL,
    (2,21,55): _UDY_FIGHT,
    (2,21,56): _UDY_STAGE_2,
    (2,21,57): _UDY_STAGE_3,
    (2,21,58): _UDY_COMPLETE.replace("collect your reward", "collect your reward from Piccolomon"),
    (2,21,59): _UDY_ACRONYM,
    (2,21,60): _UDY_OFFER,
    (2,21,61): _UDY_MISSION,
    (2,21,62): _UDY_REWARD,
    (2,21,63): _UDY_FAREWELL,
    (2,21,64): _UDY_FIGHT,
    (2,21,65): _UDY_STAGE_2,
    (2,21,66): _UDY_STAGE_3,
    (2,21,67): _UDY_COMPLETE.replace("collect your reward", "collect your reward from ExTyrannomon"),
    (2,21,68): _UDY_ACRONYM,
    (2,21,69): (
        "Investigate the skeleton ghost in Skull Seabed! Those glowing bones must hide an incredible secret!"
    ),
    (2,21,70): "Go check out the skeleton ghost in Skull Seabed!",
    (2,21,71): (
        "What? It was SkullMammothmon? I really messed up... and he still gave us this beautiful bone. "
        "That was mature of him. I need to seriously reflect. Sorry for all the trouble! Take this reward!"
    ),
    (2,21,72): "If you'll have me, could I join your team? Talk to me anytime.",
    (2,21,73): (
        "A skeleton ghost? Is that supposed to mean me? What a rude description. I challenge you to a duel!"
    ),
    (2,21,74): (
        "Hmm... You're quite skilled. Now let's hear your story. Volcanomon is interested in my glowing bone? "
        "How unusual. Very well, give him this bone."
    ),
    (2,21,75): (
        "I can understand mistaking me for a skeleton ghost. By that logic, Volcanomon must be a slag-heap ghost."
    ),
    (2,21,76): (
        "Investigate the skeleton ghost in Skull Seabed! Those glowing bones must hide an incredible secret! Raaagh!"
    ),
    (2,21,77): "Investigate the skeleton ghost in Skull Seabed! Raaagh!",
    (2,21,78): (
        "What? SkullBaluchimon? That's a serious mistake. He forgave our rudeness and even gave us the bone? "
        "He has true character. I owe him an apology. Thank you for your trouble; take this reward."
    ),
    (2,21,79): "If you'll have me, could I join your team? Talk to me anytime.",
    (2,21,80): (
        "A skeleton ghost? You mean me?! Watch your mouth! Who do you think you are?!"
    ),
    (2,21,81): (
        "Fine, I admit I lost. What did you want? Leomon wants to study my glowing bone? "
        "I don't get it, but take this one to him."
    ),
    (2,21,82): (
        "I don't want him calling me a skeleton ghost! That Leomon who hired you... "
        "wasn't half his body transparent? No? Good. Then he's still okay!"
    ),
    (2,21,83): (
        "I want to form an Angel Army! The members are Salamon, SL Angemon, and... who was the last one? "
        "Never mind. Invite another angel-like Digimon!"
    ),
    (2,21,84): (
        "Recruit members for my Angel Army: Salamon in Flower Prairie, SL Angemon at Tokona Coast, "
        "and one more angel-like Digimon in North Lost Space!"
    ),
    (2,21,85): (
        "Thank you! Take this reward. Thanks to you, we'll have the ultimate Angel Army! "
        "Their personalities are harsher than their looks suggest, though..."
    ),
    (2,21,86): (
        "You gently make even impossible wishes come true. You're more angelic than any of us! Thanks, Taiki. Bye!"
    ),
    (2,21,87): (
        "Angewomon is forming an Angel Army? You came to recruit me? Yeah, I'm in!"
    ),
    (2,21,88): (
        "I don't seem very angelic? Me?! Why not?! You can't have an angel team without me!"
    ),
    (2,21,89): "An Angel Army? Angewomon's idea, huh? Hmm... Sure, why not? I'm in.",
    (2,21,90): (
        "A lot of angel Digimon, including me, aren't great at following orders. Angels with big egos? Yeah, maybe."
    ),
    (2,21,91): (
        "An Angel Army?! Of course I'll join! When you think Babamon, you think angel; "
        "when you think angel, you think Babamon! I'm indispensable!"
    ),
    (2,21,92): (
        "Believe it or not, I was quite the knockout in my day. Everyone would faint if they saw how I looked back then!"
    ),
    (2,21,93): (
        "I want to form a Sneaky Army! Kongoumon came to mind first, then HerculesKabuterimon, and... "
        "who was the last one? Never mind. Invite another sneaky Digimon!"
    ),
    (2,21,94): (
        "Recruit members for my Sneaky Army: Kongoumon in Flower Prairie, HerculesKabuterimon at Tokona Coast, "
        "and one more sneaky Digimon in North Lost Space!"
    ),
    (2,21,95): (
        "Thank you! Take this reward. Thanks to you, we'll have the ultimate Sneaky Army! "
        "An ultimate team of sneaks sounds wonderfully contradictory."
    ),
    (2,21,96): (
        "Everyone hated the name Sneaky Army? I love it. It sounds rock-bottom, and that's perfect! "
        "Anyone who's hit the very bottom is dangerous. Remember that. Bye!"
    ),
    (2,21,97): (
        "Arukenimon is making a new team... the Sneaky Army?! That name is so lame! "
        "And I was the first Digimon she thought of?! Arukenimon! What's that supposed to mean?!"
    ),
    (2,21,98): (
        "No matter how annoyed I get, it's Arukenimon asking. I always end up helping her. Honestly..."
    ),
    (2,21,99): (
        "The Sneaky Army?! How dare you call this Hercules... What? Arukenimon came up with it? "
        "...Hmm. Fine. I'll join."
    ),
})
del (
    _GANG_RENDEZVOUS, _GANG_REWARD, _GANG_RECRUIT, _GANG_LOSS_1,
    _GANG_CHASE_1, _GANG_LOSS_2, _GANG_CHASE_2, _GANG_LOSS_3,
    _GANG_CHASE_3, _GANG_LOSS_4, _GANG_CHASE_4, _GANG_LOSS_5,
    _GANG_FINISH, _MEGAGARGO_BOAST, _MEGAGARGO_LOSS, _MEGAGARGO_APOLOGY,
    _UDY_OFFER, _UDY_MISSION, _UDY_REWARD, _UDY_FAREWELL, _UDY_FIGHT,
    _UDY_STAGE_2, _UDY_STAGE_3, _UDY_COMPLETE, _UDY_ACRONYM,
)

# Batch 3P: advanced skill tests, Piedmon Quiz 2, and TeriLop's rescue.
_ADVANCED_TEST_OFFER = (
    "Proud of your skills? Want another test? I assembled an all-new team of elite Digimon! "
    "Ta-da! They're called the Skill-Test Crew! Yeah, just ignore my naming sense. "
    "Beat them and you'll earn a huge reward. Interested now?"
)
_ADVANCED_TEST_TARGET = (
    "The Skill-Test Crew is in East Crystal Volcano. Go show them what you've got!"
)
_ADVANCED_TEST_CLEAR = (
    "You beat that lineup? Wow, that's amazing! Your skills are already top-notch, "
    "so this may be your final test. You could brag a little at this point! Here's your reward!"
)
_ADVANCED_TEST_RECRUIT = (
    "Want me on your team? I'm pretty useful! Come talk to me anytime if you're interested."
)
_ADVANCED_TEST_FIGHT = (
    "Behold! I am a legendary examiner of skill! Ta-da! The Skill-Test Crew! "
    "You hate the name? So do I. I'm taking all this awkward frustration out on you! Ready... Bomber!"
)
_ADVANCED_TEST_SECOND = (
    "All right, you pass the first round. Not bad! But I'm still not satisfied. One more battle! Ready... Bomber!"
)
_ADVANCED_TEST_FINISH = (
    "I'll let you off for today! Honestly, you've gotten so strong I could cry. "
    "Your skill truly impressed me. Go back and collect your reward!"
)
_ADVANCED_TEST_ENCOURAGE = (
    "You've come through here a few times, and you've really gotten stronger. "
    "Keep it up! I'm rooting for you!"
)
_QUIZ2_REQUEST = (
    "I have one brutal event for you. First, meet Piedmon in South Digital Space 2. "
    "Then survive his whole quiz streak. You can do it! I'd be sick of it myself... "
    "Never mind. Come back when it's over."
)
_QUIZ2_REMINDER = (
    "Find Piedmon and answer his quizzes. It sounds easy, but it's an absolute nightmare. Good luck!"
)
_QUIZ2_REWARD = (
    "Thank you! Take this reward. It's only a quiz, but Piedmon won't stop until he's satisfied. "
    "Travelers are terrified of passing through there, so we needed a sacrifi- I mean, a volunteer. "
    "Anyway, excellent work! You're our savior!"
)
_QUIZ2_RECRUIT = (
    "If you'd like, could I join your team? Come talk to me anytime you're interested."
)
_QUIZ2_WRONG = (
    "Bzzzzt! Wrong! That's a 5,000-bit fine! Just kidding... You thought I meant it? "
    "Well, jokes aside, I'm really charging you! Honk honk!"
)
_QUIZ2_BROKE = (
    "Or I would have, but you don't have enough money! Aw, that's no fun! Honk honk!"
)
_QUIZ2_SOUTH7 = (
    "The next stage is South Digital Space 7! Let's meooow!"
)
_QUIZ2_WAIT_SOUTH7 = "I'll be waiting in South Digital Space 7!"
_QUIZ2_NORTH4 = (
    "The next stage is North Digital Space 4! Let's zoooom!"
)
_QUIZ2_WAIT_NORTH4 = "I'll be waiting in North Digital Space 4!"
_QUIZ2_NORTH3 = (
    "The next stage is North Digital Space 3! Let's vroooom!"
)
_QUIZ2_WAIT_NORTH3 = "I'll be waiting in North Digital Space 3!"
_QUIZ2_NORTH8 = (
    "The next stage is North Digital Space 8! Let's squeeeak!"
)
_QUIZ2_WAIT_NORTH8 = "I'll be waiting in North Digital Space 8!"
_QUIZ2_ICE = (
    "Ding ding ding! Ice Blast is correct! It's a blast of ice. Pretty straightforward, huh? Ha haaa!"
)
_QUIZ2_BEAST = (
    "Ding ding ding! Fist of the Beast King is correct! In other words, "
    "it's the Beast King's fist! Ha haaa!"
)
_QUIZ2_TOY = (
    "Ding ding ding! Toy Flame is correct! A toy-like flame... Seriously?! Ha haaa!"
)
_QUIZ2_NOVA = (
    "Ding ding ding! Nova Blast is correct! Was that one surprisingly tough? Ha haaa!"
)
_QUIZ2_FLOWER = (
    "Ding ding ding! Flower Cannon is correct! It looks cute, but getting hit really hurts! Ha haaa!"
)
OVERRIDES.update({
    (2,21,100): (
        "Bug Digimon, myself included, tend to be helpless around strong, gorgeous women. "
        "Are bugs all masochists? Hey, don't make it sound clever!"
    ),
    (2,21,101): (
        "Wait, Arukenimon invited me?! Yes! I'm in! I'll do anything! So where are we going? "
        "What's the invitation for? ...The S-Sneaky Army? ...Oh. I see..."
    ),
    (2,21,102): (
        "She picked me just because I'm sneaky, didn't she? No, I get it. It doesn't bother me at all! "
        "...Really. Not even a little... I'm not crying! I said I'm not crying!"
    ),
    (2,21,103): _ADVANCED_TEST_OFFER,
    (2,21,104): _ADVANCED_TEST_TARGET,
    (2,21,105): _ADVANCED_TEST_CLEAR,
    (2,21,106): _ADVANCED_TEST_RECRUIT,
    (2,21,107): _ADVANCED_TEST_FIGHT,
    (2,21,108): _ADVANCED_TEST_SECOND,
    (2,21,109): _ADVANCED_TEST_FINISH.replace(
        "collect your reward", "collect your reward from Gatomon"
    ),
    (2,21,110): _ADVANCED_TEST_ENCOURAGE,
    (2,21,111): (
        "Think you're skilled? Then I'll give you a real test. I assembled an all-new team of elite Digimon! "
        "Ta-da! The Skill-Test Crew! Beat them and you'll earn a huge reward. "
        "They're waiting in East Crystal Volcano, so get moving!"
    ),
    (2,21,112): (
        "The Skill-Test Crew is in East Crystal Volcano. Hurry over there and blow them away!"
    ),
    (2,21,113): (
        "You defeated that lineup? Impressive. Your skill is so sharp that you may not need another test. "
        "Go ahead and brag a little. Here's your reward."
    ),
    (2,21,114): (
        "By the way, want me on your team? Come talk to me anytime if you do."
    ),
    (2,21,115): _ADVANCED_TEST_FIGHT,
    (2,21,116): _ADVANCED_TEST_SECOND,
    (2,21,117): _ADVANCED_TEST_FINISH.replace(
        "collect your reward", "collect your reward from Matadormon"
    ),
    (2,21,118): _ADVANCED_TEST_ENCOURAGE,
    (2,21,119): _QUIZ2_REQUEST,
    (2,21,120): _QUIZ2_REMINDER,
    (2,21,121): _QUIZ2_REWARD,
    (2,21,122): _QUIZ2_RECRUIT,
    (2,21,123): (
        "You found the great Piedmon! Special Digimon Quiz 2, Part One: "
        "What is Seadramon's signature move?"
    ),
    (2,21,124): "Ice Blast",
    (2,21,125): "Nice Hello",
    (2,21,126): "Try Again!",
    (2,21,127): _QUIZ2_ICE,
    (2,21,128): _QUIZ2_WRONG,
    (2,21,129): _QUIZ2_BROKE,
    (2,21,130): _QUIZ2_SOUTH7,
    (2,21,131): _QUIZ2_WAIT_SOUTH7,
    (2,21,132): (
        "You found the great Piedmon again! Special Digimon Quiz 2, Part Two: "
        "What is Leomon's signature move?"
    ),
    (2,21,133): "Fist of the Beast King",
    (2,21,134): "Deadly Fragments",
    (2,21,135): _QUIZ2_BEAST,
    (2,21,136): _QUIZ2_WRONG,
    (2,21,137): _QUIZ2_BROKE,
    (2,21,138): _QUIZ2_NORTH4,
    (2,21,139): _QUIZ2_WAIT_NORTH4,
    (2,21,140): (
        "Oh? You found the great Piedmon? Special Digimon Quiz 2, Part Three: "
        "What is ToyAgumon's signature move?"
    ),
    (2,21,141): "Toy Flame",
    (2,21,142): "Toy Fire",
    (2,21,143): _QUIZ2_TOY,
    (2,21,144): _QUIZ2_WRONG,
    (2,21,145): _QUIZ2_BROKE,
    (2,21,146): _QUIZ2_NORTH3,
    (2,21,147): _QUIZ2_WAIT_NORTH3,
    (2,21,148): (
        "Hey! You caught the great Piedmon! Special Digimon Quiz 2, Part Four: "
        "What is Greymon's signature move?"
    ),
    (2,21,149): "Nova Blast",
    (2,21,150): "Giga Breath",
    (2,21,151): _QUIZ2_NOVA,
    (2,21,152): _QUIZ2_WRONG,
    (2,21,153): _QUIZ2_BROKE,
    (2,21,154): _QUIZ2_NORTH8,
    (2,21,155): _QUIZ2_WAIT_NORTH8,
    (2,21,156): (
        "Oh! You found the great Piedmon! Special Digimon Quiz 2, Part Five: "
        "What is Lilymon's signature move?"
    ),
    (2,21,157): "Flower Cannon",
    (2,21,158): "Lily Smile",
    (2,21,159): _QUIZ2_FLOWER,
    (2,21,160): _QUIZ2_WRONG,
    (2,21,161): _QUIZ2_BROKE,
    (2,21,162): (
        "That's the end of the quiz! Nice work! Go collect your reward from Paildramon!"
    ),
    (2,21,163): (
        "Aw, do you miss me already? The quiz is over! Go collect your reward from Paildramon!"
    ),
    (2,21,164): _QUIZ2_REQUEST,
    (2,21,165): _QUIZ2_REMINDER,
    (2,21,166): _QUIZ2_REWARD,
    (2,21,167): _QUIZ2_RECRUIT,
    (2,21,168): _QUIZ2_ICE,
    (2,21,169): _QUIZ2_WRONG,
    (2,21,170): _QUIZ2_BROKE,
    (2,21,171): _QUIZ2_SOUTH7,
    (2,21,172): _QUIZ2_WAIT_SOUTH7,
    (2,21,173): _QUIZ2_BEAST,
    (2,21,174): _QUIZ2_WRONG,
    (2,21,175): _QUIZ2_BROKE,
    (2,21,176): _QUIZ2_NORTH4,
    (2,21,177): _QUIZ2_WAIT_NORTH4,
    (2,21,178): _QUIZ2_TOY,
    (2,21,179): _QUIZ2_WRONG,
    (2,21,180): _QUIZ2_BROKE,
    (2,21,181): _QUIZ2_NORTH3,
    (2,21,182): _QUIZ2_WAIT_NORTH3,
    (2,21,183): _QUIZ2_NOVA,
    (2,21,184): _QUIZ2_WRONG,
    (2,21,185): _QUIZ2_BROKE,
    (2,21,186): _QUIZ2_NORTH8,
    (2,21,187): _QUIZ2_WAIT_NORTH8,
    (2,21,188): _QUIZ2_FLOWER,
    (2,21,189): _QUIZ2_WRONG,
    (2,21,190): _QUIZ2_BROKE,
    (2,21,191): (
        "That's the end of the quiz! Nice work! Go collect your reward from WarGrowlmon!"
    ),
    (2,21,192): (
        "Aw, do you miss me already? The quiz is over! Go collect your reward from WarGrowlmon!"
    ),
    (2,21,193): (
        "Get me an autograph from TeriLop, the Lost Zone's ultra-superstars! You can do it, right? "
        "You're the only one on good terms with their demonic manager, LadyDevimon. "
        "I'll pay well! She's packing TeriLop's schedule at West Spiderweb Ruins right now."
    ),
    (2,21,194): (
        "Start with LadyDevimon. That schedule tyrant - or rather, actual demon - "
        "is in West Spiderweb Ruins!"
    ),
    (2,21,195): (
        "WOOOOOOOOOOO! I shouted with every ounce of strength I have! Thank you! "
        "I'm grateful enough to scream from the bottom of my heart! For now, take this reward!"
    ),
    (2,21,196): (
        "I'm exhausted from being so happy, but if you want me on your team, come talk to me anytime!"
    ),
    (2,21,197): (
        "T-T-T-TERRIBLE NEWS! Help! TeriLop has been kidnapped! Who did it? I don't know! "
        "All I know is they fled into Digital Space. Please hurry and save TeriLop!"
    ),
    (2,21,198): (
        "Please find TeriLop and rescue them! The culprit fled into Digital Space! "
        "If anything happens to those kids, I can't go on!"
    ),
    (2,21,199): (
        "Now hurry and deliver the autograph. And don't tell Numesuka or TeriLop "
        "anything about what happened! Got it?"
    ),
    (2,22,0): (
        "Trying to walk past me? Drop the act, baby. You're looking for me, me, or maybe... me. "
        "I can feel your heart pounding so hard that mine might burst too, baby!"
    ),
    (2,22,1): (
        "Your scorching heat made my heart skip a beat, baby! You nearly knocked me out, baby!"
    ),
    (2,22,2): (
        "You came to help? Thanks! I was getting lost, so I was in a real bind. "
        "Huh? Kidnapped? I don't know anything about that. I was with Numesuka and the others earlier. "
        "It's actually peaceful without fans swarming us!"
    ),
    (2,22,3): (
        "Could you check on Lopmon too? They're probably somewhere nearby..."
    ),
    (2,22,4): (
        "You came all this way to help, so we want to thank you. "
        "Could you meet us where LadyDevimon is? Lopmon and I will be waiting!"
    ),
})
del (
    _ADVANCED_TEST_OFFER, _ADVANCED_TEST_TARGET, _ADVANCED_TEST_CLEAR,
    _ADVANCED_TEST_RECRUIT, _ADVANCED_TEST_FIGHT, _ADVANCED_TEST_SECOND,
    _ADVANCED_TEST_FINISH, _ADVANCED_TEST_ENCOURAGE, _QUIZ2_REQUEST,
    _QUIZ2_REMINDER, _QUIZ2_REWARD, _QUIZ2_RECRUIT, _QUIZ2_WRONG,
    _QUIZ2_BROKE, _QUIZ2_SOUTH7, _QUIZ2_WAIT_SOUTH7, _QUIZ2_NORTH4,
    _QUIZ2_WAIT_NORTH4, _QUIZ2_NORTH3, _QUIZ2_WAIT_NORTH3,
    _QUIZ2_NORTH8, _QUIZ2_WAIT_NORTH8, _QUIZ2_ICE, _QUIZ2_BEAST,
    _QUIZ2_TOY, _QUIZ2_NOVA, _QUIZ2_FLOWER,
)

# Batch 3Q: TeriLop's reunion, the pirate rescue, and Digital Space anomalies.
_NUMESUKA_FLIRT = (
    "Hey, how are you, honey? Did you drop a gold autograph, a silver autograph, "
    "or this Numesuka autograph? None of them? Of course not, honey. "
    "What you dropped was... my heart. Isn't that right, honey?"
)
_NUMESUKA_GOODBYE = (
    "I caught those shy feelings of yours, honey. See you around, and get home safe!"
)
_LOPMON_RESCUED = (
    "Oh, did you come for me? I got tired and stopped to rest. Kidnapped? "
    "What are you talking about? I felt completely safe with Numesuka here. "
    "Numesuka? It looks like they already went home."
)
_FIND_TERRIERMON = (
    "Terriermon should be somewhere nearby too. Sorry, but could you find them?"
)
_LOPMON_RETURN = (
    "I want to thank you for coming to get me. Could you meet us where LadyDevimon is? "
    "Terriermon and I will head there first!"
)
_TERILOP_PANIC = (
    "T-T-T-TERRIBLE NEWS! Help! TeriLop has been kidnapped! Who did it? I don't know! "
    "All I know is they fled into Digital Space. Please hurry and save TeriLop!"
)
_TERILOP_RESCUE_REMINDER = (
    "Please find TeriLop and rescue them! The culprit fled into Digital Space! "
    "If anything happens to those kids, I can't go on!"
)
_TERILOP_SECRET = (
    "Now hurry and deliver the autograph. And don't tell Numesuka or TeriLop "
    "anything about what happened! Got it?"
)
_TERRIERMON_RESCUED = (
    "You came to help? Thanks! I was getting lost, so I was in a real bind. "
    "Huh? Kidnapped? I don't know anything about that. I was with Numesuka and the others earlier. "
    "It's actually peaceful without fans swarming us!"
)
_FIND_LOPMON = "Could you check on Lopmon too? They're probably somewhere nearby..."
_TERRIERMON_RETURN = (
    "You came all this way to help, so we want to thank you. "
    "Could you meet us where LadyDevimon is? Lopmon and I will be waiting!"
)
_PIRATE_RESCUE = (
    "Remember Mermaimon, boss of the Western Pirates? Something incredibly dangerous captured her! "
    "At this rate, she's obviously doomed. We thought about rescuing her ourselves, "
    "but there's no way we can win. You're our only hope! Please save our precious crewmate!"
)
_PIRATE_COAST = (
    "Save Mermaimon at Tokona Coast! Divermon is keeping her from being dragged away, "
    "but the enemy is far stronger. They won't last much longer!"
)
_PIRATE_NEED_TREASURE = (
    "You saved Mermaimon? Thank you! But... didn't she give you a treasure? "
    "Pirate law says she owes one to whoever saves her life. Sorry to send you back and forth, "
    "but return after you receive it."
)
_PIRATE_TREASURE = (
    "You got Mermaimon's treasure. On behalf of the Pirates, thank you again. "
    "You truly saved us! In exchange for that treasure, I'll give you this Melody."
)
_PIRATE_REWARD = "And please accept this reward from all of us."
_MERMAIMON_DRAGGED = (
    "Mermaimon was dragged into the sea! P-please, save her!"
)
_MERMAIMON_SEA = (
    "She was dragged in from here, so she must be in Tokona Sea by now. "
    "Please hurry and save Mermaimon!"
)
_MERMAIMON_HUNT = (
    "Find four treasures around Tokona Sea and Tokona Coast. As thanks, I'll let you keep one! "
    "They'll vanish once I leave, so find my feelings - I mean, the treasures - quickly!"
)
_TAKE_YES = "Yes, take it!"
_TAKE_NO = "No, leave it."
OVERRIDES.update({
    (2,22,5): _NUMESUKA_FLIRT,
    (2,22,6): _NUMESUKA_GOODBYE,
    (2,22,7): _LOPMON_RESCUED,
    (2,22,8): _FIND_TERRIERMON,
    (2,22,9): _LOPMON_RETURN,
    (2,22,10): (
        "TeriLop, the Lost Zone's shining superstars! Is it true you can get their autograph? "
        "That terrifying monochrome manager, LadyDevimon, doesn't even scare you! "
        "Please help, and I'll reward you properly. She's in West Spiderweb Ruins now!"
    ),
    (2,22,11): (
        "Start with their manager, LadyDevimon. That monochrome, old-fashioned lady "
        "is in West Spiderweb Ruins."
    ),
    (2,22,12): (
        "EEEEEEEEEEK! I nearly shattered glass with that scream of joy! "
        "I'm grateful enough to shout from the bottom of my heart! "
        "I'm exhausted from all the excitement, but please take this reward!"
    ),
    (2,22,13): (
        "Would you like me on your team? Come talk to me anytime if you do!"
    ),
    (2,22,14): _TERILOP_PANIC,
    (2,22,15): _TERILOP_RESCUE_REMINDER,
    (2,22,16): _TERILOP_SECRET,
    (2,22,17): (
        "Trying to walk past me? Drop the act, baby. You're looking for me, me, or maybe... me. "
        "I can feel your heart pounding so hard that mine might burst too, baby!"
    ),
    (2,22,18): (
        "Your scorching heat made my heart skip a beat, baby! You nearly knocked me out, baby!"
    ),
    (2,22,19): _TERRIERMON_RESCUED,
    (2,22,20): _FIND_LOPMON,
    (2,22,21): _TERRIERMON_RETURN,
    (2,22,22): _NUMESUKA_FLIRT,
    (2,22,23): _NUMESUKA_GOODBYE,
    (2,22,24): _LOPMON_RESCUED,
    (2,22,25): _FIND_TERRIERMON,
    (2,22,26): _LOPMON_RETURN,
    (2,22,27): _PIRATE_RESCUE,
    (2,22,28): _PIRATE_COAST,
    (2,22,29): _PIRATE_NEED_TREASURE,
    (2,22,30): _PIRATE_TREASURE,
    (2,22,31): _PIRATE_REWARD,
    (2,22,32): (
        "Everyone hates us and treats us like jokes, but you always faced us honestly. "
        "Thank you, Taiki. You're a good person."
    ),
    (2,22,33): _MERMAIMON_DRAGGED,
    (2,22,34): _MERMAIMON_SEA,
    (2,22,35): _MERMAIMON_HUNT,
    (2,22,36): (
        "Oh, you chose that one? Hee hee... It's very you. Show it to MarineDevimon."
    ),
    (2,22,37): "Take the Fire Crown?",
    (2,22,38): _TAKE_YES,
    (2,22,39): _TAKE_NO,
    (2,22,40): "Take the Snow Crown?",
    (2,22,41): _TAKE_YES,
    (2,22,42): _TAKE_NO,
    (2,22,43): "Take the Saint Crown?",
    (2,22,44): _TAKE_YES,
    (2,22,45): _TAKE_NO,
    (2,22,46): "Take the Dark Crown?",
    (2,22,47): _TAKE_YES,
    (2,22,48): _TAKE_NO,
    (2,22,49): (
        "Glub?! Remember Mermaimon, boss of the Western Pirates? Something incredibly dangerous captured her! "
        "At this rate, she's obviously doomed. We leftover pirates thought about rescuing her, "
        "but that's completely impossible. You're our only hope! Please save our precious crewmate!"
    ),
    (2,22,50): (
        "Save Mermaimon at Tokona Coast! MarineDevimon is keeping her from being dragged away, "
        "but the enemy is far stronger. They won't last much longer!"
    ),
    (2,22,51): _PIRATE_NEED_TREASURE,
    (2,22,52): _PIRATE_TREASURE,
    (2,22,53): _PIRATE_REWARD,
    (2,22,54): (
        "We meant to disband, but this mess pulled us back together. "
        "Before we knew it, the Eastern Pirates had returned. We may start over as a real pirate crew. "
        "That's half thanks to you and half your fault. I don't know what to say, but I am grateful!"
    ),
    (2,22,55): _MERMAIMON_DRAGGED,
    (2,22,56): _MERMAIMON_SEA,
    (2,22,57): _MERMAIMON_HUNT,
    (2,22,58): (
        "Oh, you chose that one? Hee hee... It's very you. Show it to Divermon."
    ),
    (2,22,59): "Take the Fire Crown?",
    (2,22,60): _TAKE_YES,
    (2,22,61): _TAKE_NO,
    (2,22,62): "Take the Snow Crown?",
    (2,22,63): _TAKE_YES,
    (2,22,64): _TAKE_NO,
    (2,22,65): "Take the Saint Crown?",
    (2,22,66): _TAKE_YES,
    (2,22,67): _TAKE_NO,
    (2,22,68): "Take the Dark Crown?",
    (2,22,69): _TAKE_YES,
    (2,22,70): _TAKE_NO,
    (2,22,71): (
        "I found a suspicious stone tablet in the Spiderweb Underpass. "
        "It looked so ominous that I was too scared to touch it, but I can't stop thinking about it. "
        "Could you investigate it for me?"
    ),
    (2,22,72): (
        "Investigate the stone tablet I found in the Spiderweb Underpass. "
        "It's so suspicious that you can't miss it."
    ),
    (2,22,73): (
        "Thanks! Did you investigate the tablet? A guardian-like voice spoke from it? "
        "'Do not break the seal. Do not wake the sleeper.' What is sealed, and who's sleeping? "
        "For now, please take this reward."
    ),
    (2,22,74): (
        "Thank you, Taiki. I'll search our data for anything about that suspicious tablet."
    ),
    (2,22,75): (
        "I found two more suspicious tablets! One is in Papyrus Cave, and the other is below Crystal Volcano. "
        "The guardian said it was coming out, so I ran. Could you investigate them too?"
    ),
    (2,22,76): (
        "The suspicious tablets are in Papyrus Cave and below Crystal Volcano!"
    ),
    (2,22,77): (
        "Thank you, Taiki! Take this reward. That tablet guardian sounds furious. "
        "Maybe it wakes up cranky and wants to stay asleep... or maybe somebody did something awful enough to anger it."
    ),
    (2,22,78): (
        "I feel like a little more research will reveal something. I'll contact you when I learn more!"
    ),
    (2,22,79): (
        "I found another suspicious tablet in Stealth Cave! This time, it really feels like something is there. "
        "Could you investigate one more time?"
    ),
    (2,22,80): (
        "Investigate the suspicious tablet in Stealth Cave. This one feels genuinely dangerous, so be careful!"
    ),
    (2,22,81): (
        "Thank you! How did it go? ...I see. AncientWisemon was angering the tablet guardian "
        "by reviving Ancient Digimon to conquer the world? Anyone would be furious about that. "
        "And the guardian gave you a DigiScore for helping? Wow! This becomes Shoutmon X3SD. "
        "I'll tune it so you can use it... There, all done!"
    ),
    (2,22,82): "Please take this reward from me too!",
    (2,22,83): (
        "The mystery that bothered me for so long is finally solved. Now I can relax. Thank you, Taiki!"
    ),
    (2,22,84): (
        "We've had lots of strange reports from Digital Space lately. I went to investigate and met Parrotmon. "
        "It was looking for you, Taiki. Could you go see what it wants?"
    ),
    (2,22,85): (
        "Parrotmon is looking for you, Taiki. Could you go to East Digital Space?"
    ),
    (2,22,86): (
        "It wasn't Parrotmon? It was some kind of copy, and it kept multiplying? "
        "What exactly was that thing? Something strange is definitely happening in Digital Space. "
        "For now, here's your reward!"
    ),
    (2,22,87): (
        "If anything changes, I'll let you know, Taiki. I may need your help again."
    ),
    (2,22,88): (
        "Strange things are happening all over this Zone, and the amount of data is growing abnormally fast. "
        "Remember what the fake Parrotmon said? East Digital Space is acting especially strange. "
        "Could you find out what's happening?"
    ),
    (2,22,89): (
        "The amount of data in East Digital Space is swelling for no apparent reason. "
        "Could you investigate?"
    ),
    (2,22,90): (
        "A Digimon is copying itself and multiplying endlessly?! That sounds incredibly dangerous. "
        "But what could it gain from doing that? For now, take this reward."
    ),
    (2,22,91): (
        "Digimon do weird things everywhere, but none of them ever think about the consequences. "
        "I'll investigate a little more and may ask for your help again."
    ),
})
del (
    _NUMESUKA_FLIRT, _NUMESUKA_GOODBYE, _LOPMON_RESCUED,
    _FIND_TERRIERMON, _LOPMON_RETURN, _TERILOP_PANIC,
    _TERILOP_RESCUE_REMINDER, _TERILOP_SECRET, _TERRIERMON_RESCUED,
    _FIND_LOPMON, _TERRIERMON_RETURN, _PIRATE_RESCUE, _PIRATE_COAST,
    _PIRATE_NEED_TREASURE, _PIRATE_TREASURE, _PIRATE_REWARD,
    _MERMAIMON_DRAGGED, _MERMAIMON_SEA, _MERMAIMON_HUNT,
    _TAKE_YES, _TAKE_NO,
)

# Batch 3R: Kuramon's data surge, DigiNoir errands, and fan side quests.
OVERRIDES.update({
    (2,22,92): (
        "Taiki, there's an emergency in North Lost Space! The amount of data is exploding. "
        "If this continues, Digimon will get hurt. Please stop whatever is causing it!"
    ),
    (2,22,93): (
        "The emergency is in North Lost Space. I don't know what's behind it, "
        "but please stop the source of the trouble!"
    ),
    (2,22,94): (
        "What?! Kuramon was behind it? Honestly, I'm relieved, but a tiny bit disappointed. "
        "I expected some terrifying mastermind! I'll process the data it gave you so you can use it... "
        "There! This is Shoutmon X3GM!"
    ),
    (2,22,95): "And please accept this reward from me!",
    (2,22,96): "Thank you, Taiki! I knew I could count on you!",
    (2,22,97): (
        "Please bring me the legendary, unbelievably delicious snack hidden in West Spiral Amazon: "
        "the Ultimate DigiNoir!"
    ),
    (2,22,98): (
        "Rumor says the Ultimate DigiNoir is somewhere in West Spiral Amazon. "
        "I've never seen or tasted it, so it really is only a rumor..."
    ),
    (2,22,99): (
        "Thank you! Wow, it looks incredible! Here's your reward, and now... time to eat! "
        "...Wh-what is this?! It's s-so... so delicious! Too delicious! "
        "It truly is the Ultimate DigiNoir!"
    ),
    (2,22,100): (
        "That was the best thing I've ever eaten. The box said 76 peta-DigiCalories, though. "
        "Kilo, mega, giga, tera, then peta... Uh... You know what? Never mind! Thanks! Bye!"
    ),
    (2,22,101): (
        "Devimon stole a memory card full of important data! I absolutely can't lose it. "
        "Please get it back!"
    ),
    (2,22,102): (
        "The Devimon who stole my memory card is in East Digital Space. Please recover it!"
    ),
    (2,22,103): (
        "Thank you! If I'd lost this memory, I couldn't have kept living in this Zone... "
        "in a certain sense. That's how important it is."
    ),
    (2,22,104): (
        "It was full of suspicious files? H-how do you know that?! Devimon told you? "
        "Did you see what's inside?! You didn't? Really?! Thank goodness I locked my original poetry... "
        "N-never mind that! Anyway, thanks!"
    ),
    (2,22,105): (
        "Huh? The memory card? No way I'm returning it, devi! Why? That's none of your business, devi! "
        "If you want it back, try beating me!"
    ),
    (2,22,106): (
        "All right, I surrender, devi! Something about Terriermon looks shady and annoys me, "
        "so I wanted to teach him a lesson. I tossed the memory card somewhere in Fort Yard. "
        "It had weird files, but I couldn't open them. Go find it yourself, devi!"
    ),
    (2,22,107): (
        "I threw the memory card somewhere in Fort Yard. A quick search should find it. "
        "That thing was strange, though - it hid mountains of locked files. "
        "Terriermon is definitely shady, devi."
    ),
    (2,22,108): (
        "Leomon is always patrolin' to keep us safe. Would ya deliver this DigiNoir to him as our thanks?"
    ),
    (2,22,109): (
        "Leomon should be at Knuckle Coast now. Sorry for the trouble, but take him that DigiNoir!"
    ),
    (2,22,110): (
        "Thank ya kindly! He liked it? Then I owe you some thanks too."
    ),
    (2,22,111): (
        "What we gave Leomon wasn't anything fancy. Long as our gratitude reached him, that's enough. "
        "That's what really matters, right?"
    ),
    (2,22,112): (
        "Tentomon and the others sent me this DigiNoir? Thank you for delivering it! "
        "Please tell them I appreciate it."
    ),
    (2,22,113): (
        "I don't patrol because I want thanks. I actually tried to do it without anyone noticing. "
        "But the people who care really do notice... I'm honestly touched."
    ),
    (2,22,114): (
        "Piedmon's pranks have crossed the line lately. He's in the Dark Tunnel now. "
        "Go give him one serious punishment!"
    ),
    (2,22,115): "Punish Piedmon for his pranks in the Dark Tunnel!",
    (2,22,116): (
        "You taught Piedmon a lesson? Really? Thank you! Things should stay quiet for a while."
    ),
    (2,22,117): (
        "If Piedmon starts pulling pranks again, I'll ask you to punish him one more time!"
    ),
    (2,22,118): (
        "Stop playing pranks? You've gotta be kidding! I'll blast anyone who gets in my way! "
        "Got a problem? Come at me!"
    ),
    (2,22,119): (
        "...I came at you, and you blasted me. Fine, I'll stop the pranks for a while. "
        "Huh? Okay, that was a lie! I'll stop! I'll never do it again!"
    ),
    (2,22,120): (
        "Never pulling another prank for the rest of my life... It feels like there's a hole in my heart."
    ),
    (2,22,121): (
        "My friend Agumon hasn't returned from exploring. He may be hurt, and I'm worried sick! "
        "Please help him in West Knuckle Coast!"
    ),
    (2,22,122): (
        "Agumon went to West Knuckle Coast and never came back. Please hurry and help him!"
    ),
    (2,22,123): (
        "Thank you so much for helping Agumon! Here's your reward. Really, thank you!"
    ),
    (2,22,124): (
        "Now that I know he's safe, all the strength left my body. I'm going home..."
    ),
    (2,22,125): "Ugh... I can't go on. If only I had a bandage...",
    (2,22,126): "Give him a Bandage?",
    (2,22,127): "Yes, give it.",
    (2,22,128): "No, don't.",
    (2,22,129): (
        "...Huh?! Th-thank you! You brought me back to life! Gabumon sent you? "
        "What a great friend! Please thank Gabumon when you return!"
    ),
    (2,22,130): "...You don't have a Bandage.",
    (2,22,131): (
        "Ugh... I may not make it. I'm getting dizzy... Somebody help... Gabumon..."
    ),
    (2,22,132): (
        "Thank you! I'm okay now. Please go back and thank Gabumon for me!"
    ),
    (2,22,133): (
        "My pale skin really bothers me. I'd love a nice golden tan like Wendimon's! "
        "Ask Wendimon for his tanning secret. He's in the Dark Tunnel."
    ),
    (2,22,134): (
        "Ask Wendimon in the Dark Tunnel for his tanning secret."
    ),
    (2,22,135): (
        "Wow! With this, I'll finally have a perfect golden tan! Thank you! Here's your reward."
    ),
    (2,22,136): (
        "I'll try it as soon as I get home. I've dreamed of bronze skin! I'm so excited!"
    ),
    (2,22,137): (
        "Huh? You have a question for me? Ask anything! You want to know how I got my tan? "
        "I'm naturally dark! This isn't a tan!"
    ),
    (2,22,138): (
        "Ow! What was that for? Fine, fine! Take this. It's my secret item!"
    ),
    (2,22,139): (
        "If he wants a tan, use that. Rub it on, go outside, and he'll turn amazingly golden. "
        "Hurry and take it to him."
    ),
    (2,22,140): (
        "Honestly, I'd rather have pale skin. I only bought that lotion because "
        "I mistook it for Status Guard..."
    ),
    (2,22,141): (
        "I want to soar through the sky with grace, freedom, and power! "
        "My dream is to join the Digimon Air Corps. Ask other bird Digimon how they train so I can learn from them!"
    ),
    (2,22,142): (
        "Where can you find bird Digimon? All over the place! Travel around and you'll meet some eventually!"
    ),
    (2,22,143): (
        "...I see. None of that was remotely useful, but somehow I feel much less worried. "
        "Please take this reward."
    ),
    (2,22,144): "Thanks! See you!",
    (2,22,145): (
        "Training to fly? Running is faster than flying! Look at these thighs! Awesome, right? "
        "Tell your friend to quit worrying about it!"
    ),
    (2,22,146): "My training is one hundred running drills!",
    (2,22,147): (
        "Training to fly? Penguinmon doesn't fly. Sliding is better. "
        "Penguinmon doesn't train. Sleeping is better."
    ),
    (2,22,148): (
        "Penguinmon doesn't fly or train. Penguinmon hates hot weather and hot-blooded Digimon."
    ),
    (2,22,149): (
        "Training to fly? DaiPenmon doesn't fly and doesn't want to. "
        "If you want to fly, why not ride an airplane?"
    ),
    (2,22,150): (
        "DaiPenmon doesn't fly. It's not that I can't; I simply don't want to."
    ),
    (2,22,151): (
        "I love idols! I love them so much I can't stand it! S-sorry, I got carried away... Nuh-huh! "
        "You know the rookie duo Terriermon and Lopmon, right? Teri-lori-lop, TeriLop! "
        "The superstars of tomorrow! I want to give them a present, but their manager LadyDevimon "
        "is so terrifying no fan can approach. Would you deliver it for me? Nuh-huh-huh!"
    ),
    (2,22,152): (
        "First, ask the manager where TeriLop is. That's the first and hardest part. "
        "My fan network says LadyDevimon is in West Spiderweb Ruins. I'm counting on you... Nuh-huh!"
    ),
    (2,22,153): (
        "You're back! Did you deliver it? ...Wh-what is this?! Nuh-ho-ho-ho! TeriLop's autograph?! "
        "They were still designing it, and just finished? Then this is the very first one?! "
        "That's incredible! Thank you! Take your reward! Nuh-huh-huh!"
    ),
    (2,22,154): (
        "TeriLop is about to become huge! There's absolutely no doubt! "
        "Keep supporting them: Teri-lori-lop! Nuh-huh!"
    ),
    (2,22,155): (
        "Who are you? A TeriLop fan with a present? Absolutely not! "
        "This is the most important point in their careers. I can't pass along some mystery gift. "
        "If you insist, you'll have to defeat me!"
    ),
    (2,22,156): (
        "Oh, you're strong! And you don't look bad either. You might be useful someday. "
        "Fine, I'll pretend to trust you. They're resting in East Knuckle Coast. "
        "Go now if you want to meet them directly."
    ),
    (2,22,157): (
        "Your strength and decent looks earned special treatment. TeriLop is resting in East Knuckle Coast. "
        "You can meet them directly right now."
    ),
    (2,22,158): (
        "You're our fan? And this is a present?! Wow! Thank you! We just debuted, "
        "so this is our first gift ever! We want you to have our autograph in return. "
        "Lopmon has it. We spent ages designing it and just finished!"
    ),
    (2,22,159): (
        "We worked really hard to design this autograph together. "
        "We want our very first fan to have it!"
    ),
    (2,22,160): (
        "You're... a fan? And that's a handmade present?! Wow, I feel like a real idol! "
        "N-no, I... Wait... S-sorry! This is awful. I'm stammering in front of our first-ever fan. "
        "I might cry, so could you give the present to Terriermon?"
    ),
    (2,22,161): (
        "Thank you for supporting us. Please accept the TeriLop autograph we designed together "
        "for our very first fan, plus these brand-new special goods. "
        "Ignore my robotic voice. Teri-lori-lop! And the sweat, cracking voice, wandering eyes, "
        "and shaking knees are all your imagination!"
    ),
    (2,22,162): (
        "We're still bad at singing, dancing, autographs, and smiling, but we'll keep working "
        "until we're great at all of it! So please support us! We beg you!"
    ),
    (2,22,163): (
        "Lately, strange noises near my house keep me awake: MOGEEE! HOGEEE! "
        "Find the source and punish whoever's making that racket in West Spiral Amazon!"
    ),
    (2,22,164): (
        "...Huh?! I nodded off. It's so peaceful here. "
        "Please silence the noisy Digimon in West Spiral Amazon!"
    ),
    (2,22,165): (
        "You defeated them?! Thank you! Now I can finally get a good night's sleep. Take this reward!"
    ),
    (2,22,166): "Thank you. Good night...",
    (2,22,167): (
        "Someone's yelling HOGEEE and MOGEEE? That's my lord ShogunGekomon's singing, ribbit. "
        "He's nearby, but he's scary when he's angry, ribbit!"
    ),
    (2,22,168): (
        "My lord ShogunGekomon is somewhere nearby, ribbit. "
        "I don't know what he'll do if you make him angry!"
    ),
})

# Batch 3S: NumeSuka publicity, Pharaohmon's former army, and pirate cleanup.
OVERRIDES.update({
    (2,22,169): (
        "HOGE HOGEEE! HOGE-HOGE-HOGEGEEE! What?! What do you mean, 'too loud,' ribbit?! "
        "Now I'm angry. Completely, totally angry!"
    ),
    (2,22,170): (
        "Grrr... Fine, ribbit. I'll sing a little more quietly. Happy now?"
    ),
    (2,22,171): "...Hoge hogeee! A little softer than usual!",
    (2,22,172): (
        "Get me an autograph from the Lost Zone's greatest filthy idol duo, Numemon and Sukamon! "
        "First, meet their manager LadyDevimon in West Spiderweb Ruins!"
    ),
    (2,22,173): (
        "To get Numemon and Sukamon's autograph, start with their manager LadyDevimon "
        "in West Spiderweb Ruins!"
    ),
    (2,22,174): (
        "WOOOOAH! Ugh, that reeks! This is the legendary handwritten NumeSuka autograph! "
        "They say everyone who holds it sheds tears. Getting one is practically life-threatening! "
        "Cough! Sorry, it caught in my throat. Th-thank you! Please... cough... take this reward!"
    ),
    (2,22,175): (
        "The rumor says everyone who gets one cries. Now I know why: "
        "the smell makes your eyes burn! B-but never mind that. Cough... Thank you!"
    ),
    (2,22,176): (
        "A NumeSuka autograph? Absolutely not! Or that's what I'd usually say, "
        "but those two have almost no fans. We need to cherish every one. "
        "Promote NumeSuka to three Digimon nearby and hand out these goods. "
        "Report back when you're done, then you can ask for the autograph!"
    ),
    (2,22,177): (
        "Promote NumeSuka to three Digimon nearby and hand out their goods. "
        "Report back when you're finished!"
    ),
    (2,22,178): (
        "Looks like you promoted them properly! NumeSuka is lucky to have a fan like you. "
        "They're rehearsing their corny lines in South Papyrus Desert. "
        "Try not to faint from the smell!"
    ),
    (2,22,179): (
        "NumeSuka is in South Papyrus Desert, practicing how to make fans swoon. "
        "Their lines and their smell are equally cheesy, so brace yourself!"
    ),
    (2,22,180): (
        "NumeSuka? They sound kinda smelly, chirp. You're promoting them everywhere? "
        "You must really like them. Is that photo card for me? Th-thanks, chirp."
    ),
    (2,22,181): (
        "NumeSuka... I remember the name and faces now, chirp! "
        "They look smelly too, but I'll try rooting for them."
    ),
    (2,22,182): (
        "NumeSuka?! Of course I know them! That ultra-rare filthy duo has a cult following! "
        "They smell so bad they're banned from live venues, and even their CD makes you dizzy. "
        "They're the best at being the worst and the worst at being the best! "
        "Be proud to call yourself a fan. I'll take a postcard too..."
    ),
    (2,22,183): (
        "I'll write to my friend who loves bizarre stuff. "
        "I'll use a creepy NumeSuka-style line that'll send chills down their spine!"
    ),
    (2,22,184): (
        "WHAT?! NumeSuka?! I love them! I'm a massive fan! "
        "You're giving me this freshly printed, strongly scented photo?! Thank you! This is awesome!"
    ),
    (2,22,185): (
        "This is incredibly rare! Nobody else can have one. "
        "It smells so strong that tears won't stop... I mean, I'm crying because I'm happy! Thanks!"
    ),
    (2,22,186): (
        "Welcome, baby. Are your eyes watering because of my piercing smile, "
        "or my piercing smell? Either way, this NumeSuka autograph will knock you out!"
    ),
    (2,22,187): (
        "Let this NumeSuka autograph knock you out. Sweet dreams, baby. "
        "I wrote it for you with overflowing love and dripping slime!"
    ),
    (2,22,188): (
        "Hey, how are you? Welcome, honey. You look ready to faint. "
        "You want our NumeSuka autograph? Ask my partner Numemon, honey."
    ),
    (2,22,189): (
        "Get the NumeSuka autograph from Numemon, honey. "
        "We put enough heart into it to numb your nose!"
    ),
    (2,22,190): (
        "I came from Phantom Palace, but I lost my pass and can't get home. "
        "Could you ask the gatekeeper to let me through? She's in East Digital Space."
    ),
    (2,22,191): (
        "The Phantom Palace gatekeeper is in East Digital Space. "
        "Please ask her to let me through without a pass."
    ),
    (2,22,192): (
        "Thank you! I can finally go home. I'll never forget this favor. Please take this reward."
    ),
    (2,22,193): "Thanks again. Bye!",
    (2,22,194): (
        "Let someone through without a pass? Of course not. But Angewomon has an adorable hair tie... "
        "Bring it to me and I might reconsider. She's in East Knuckle Coast."
    ),
    (2,22,195): (
        "Bring me one of Angewomon's hair ties! She's in East Knuckle Coast."
    ),
    (2,22,196): "Ooh, I'm excited! Which one did you bring?",
    (2,22,197): "Which one will you give her?",
    (2,22,198): "Marimo Hair Tie",
    (2,22,199): "Strawberry Hair Tie",
    (2,23,0): (
        "What is this?! It isn't cute! Not even a little! "
        "It's shaggy, soggy, plain, cheap, and absolutely awful!"
    ),
    (2,23,1): (
        "I cooled down and looked again. Maybe this understated-cute style actually works. "
        "I'm sorry I said such awful things before."
    ),
    (2,23,2): "Oh, how cute! I love it!",
    (2,23,3): (
        "Tell your friend she may use this road whenever she likes!"
    ),
    (2,23,4): (
        "Honestly, I would've accepted anything Angewomon owned. She has such good taste!"
    ),
    (2,23,5): (
        "A hair tie? Sure! I have strawberry and marimo ones. "
        "I'm not using either right now, so you can have both!"
    ),
    (2,23,6): (
        "You're giving them to someone, right? Remember this: choosing strawberry means "
        "she's straightforward. Choosing marimo means she knows exactly who she is."
    ),
    (2,23,7): (
        "When Pharaohmon disappeared, all his followers scattered. Not that this mummy owes him anything, "
        "but he'll be crushed if he returns to an empty army. Could you gather them again? "
        "They're at Knuckle Coast and North Stealth Valley."
    ),
    (2,23,8): (
        "Help me rebuild Pharaohmon's army. Gather his former followers "
        "at Knuckle Coast and North Stealth Valley."
    ),
    (2,23,9): (
        "Thank you. Take your reward, then forget all about this. ...The celebration is over."
    ),
    (2,23,10): (
        "I spoke to the old followers afterward. Pharaohmon is never coming back. "
        "You knew that from the beginning, didn't you? Yet you still helped. "
        "I can't tell whether you're kind or cruel."
    ),
    (2,23,11): (
        "You want to rebuild Pharaohmon's army, shell? If this is a joke, it isn't funny. "
        "If you're picking a fight, I'll gladly take you on!"
    ),
    (2,23,12): (
        "You truly want to rebuild Pharaohmon's army, shell? Fine by me. "
        "There's only one problem: who leads it? Only Lord Pharaohmon could hold that army together."
    ),
    (2,23,13): (
        "Pharaohmon's army is part of my past, shell. You can ask the other followers, "
        "but I think they'll give you the same answer."
    ),
    (2,23,14): (
        "Ribbit?! Pharaohmon's army is coming back?! Then Lord Pharaohmon returned?! "
        "He didn't? Mummymon just suggested it?! Are you making fun of me?!"
    ),
    (2,23,15): (
        "...I already knew, ribbit. Lord Pharaohmon can never return. "
        "Before he vanished, he gathered us and told us to live freely and happily in brighter places. "
        "The army exists only in our memories now."
    ),
    (2,23,16): (
        "The bright, happy place Lord Pharaohmon described... "
        "Do you think I'll find it somewhere someday, ribbit?"
    ),
    (2,23,17): (
        "You want to rebuild Pharaohmon's army, evil? If you're serious, you're a fool. "
        "If you're mocking us, I'll make you regret it!"
    ),
    (2,23,18): (
        "You truly want the army together again, evil? I don't mind gathering. "
        "It really was a good army. We lost someone irreplaceable. Give Mummymon my regards."
    ),
    (2,23,19): (
        "I'd be happy to reunite with Pharaohmon's army someday, evil. "
        "It would be more like a class reunion now. Tell Mummymon I'm looking forward to it!"
    ),
    (2,23,20): (
        "Defeat the pirate crews terrorizing Tokona Sea! Beat all four crews - east, west, north, and south - "
        "and recover the stolen treasures. They're all around Tokona Sea. Good luck!"
    ),
    (2,23,21): (
        "Defeat all four pirate crews around Tokona Sea and recover the stolen treasures!"
    ),
    (2,23,22): (
        "You did it! You're even better than the rumors say. Please accept our reward. "
        "Thank you - you truly saved us!"
    ),
    (2,23,23): (
        "Thanks to you, peace has returned to Tokona Sea. Everyone is grateful. Farewell!"
    ),
    (2,23,24): (
        "Glub?! You picked a fight with us?! We are the startling pirates of the east, "
        "the Eastern Pirates! No questions asked - we'll blow you away!"
    ),
    (2,23,25): (
        "Glub?! We lost?! Take this Silver Bar and forgive us! "
        "We are the defeated pirates of the east, the Eastern Losers! No questions asked - we disband!"
    ),
    (2,23,26): (
        "Even among pirate crews, only the Eastern Pirates felt more like a club. "
        "We all knew why: we're nothing but minor goons, and we don't even have a leader..."
    ),
    (2,23,27): (
        "You know who we are! The hot pirates of the south, the Southern Pirates! "
        "No questions asked - we'll blow you away!"
    ),
    (2,23,28): (
        "We didn't lose in strength. We only lost in toughness! If you'll let us keep that much pride, "
        "we might give you this Giant Pearl. What, that's cheap? Call it adult negotiation!"
    ),
    (2,23,29): (
        "Adult pirates are always fighting society! Gomamon once asked me, with sparkling eyes, "
        "'Mister, you're an adult, so why are you still playing pirates?' "
        "I had to ask him to repeat it. Innocent or not, that still ticks me off!"
    ),
    (2,23,30): (
        "You want to defeat us? Then try it. We are the alluring pirates of the west, "
        "the Western Pirates! No questions asked - I'll blow you away!"
    ),
    (2,23,31): (
        "Oh, I lost. You're better than expected. You want our treasure? "
        "Hee hee... You're more pirate-like than we are. Take this Heart Sapphire. "
        "If I could, I'd give you my heart too."
    ),
    (2,23,32): (
        "You could become a finer pirate than any of us. Whether that would make you happy is another question!"
    ),
    (2,23,33): (
        "I know you came to defeat us. Well, that won't go swimmingly - squid or no squid! "
        "We are the cold pirates of the north, the Northern Pirates! No questions asked - we'll blow you away!"
    ),
    (2,23,34): (
        "Fine, we surrender. Tentacles up! Take this Gold Crown and leave us alone."
    ),
    (2,23,35): (
        "We don't really seem like pirates. What do we seem like instead? No idea. "
        "Personally, I'm pretty happy with us as we are."
    ),
    (2,23,36): (
        "A troublesome super-VIP is visiting Flower Prairie. I need you to provide the hospitality "
        "only you can manage. You'll know the guest immediately. This will be difficult, but please help!"
    ),
    (2,23,37): (
        "Please entertain the super-VIP in Flower Prairie without upsetting him. "
        "It won't be easy, but I'm counting on you!"
    ),
    (2,23,38): (
        "Thank you! I'm truly grateful. Please take this reward. "
        "For dealing with someone that difficult, you deserve a medal!"
    ),
    (2,23,39): "I'll be going now. Thank you again!",
    (2,23,40): (
        "Hmm! You may approach! I am the Super-VIP himself, PrinceMamemon! "
        "First, I'm hungry. Give me ten Revival Medicines."
    ),
    (2,23,41): "Give him 10 Revival Medicines?",
    (2,23,42): "Yes, give them.",
    (2,23,43): "No, don't.",
    (2,23,44): (
        "Hmm! Acceptable! Now that my stomach is full, I want a gift for my beautiful queen. "
        "Bring me a flower the color of passion!"
    ),
    (2,23,45): (
        "What?! You don't have ten Revival Medicines? You're useless! "
        "Bring me ten at once!"
    ),
    (2,23,46): (
        "Why are you standing around? Bring me ten Revival Medicines at once!"
    ),
    (2,23,47): (
        "Bring me a flower the color of passion! What are you waiting for? Hurry!"
    ),
})

# Batch 3T: Game Kingdom, Sakuyamon's secret, and Calumon's hide-and-seek.
_CALUMON_FOUND = "Aww, you found me! You got me, calu!"
OVERRIDES.update({
    (2,23,48): (
        "Hmm... That may be passionate, but it isn't quite right. "
        "Bring me a flower with a sexier color!"
    ),
    (2,23,49): (
        "Stop standing around! Bring me a flower with a sexy color! Hurry up!"
    ),
    (2,23,50): (
        "Hmm! Most acceptable! Combined with the first flower, I am thoroughly satisfied. "
        "Perhaps some things truly cannot be bought with money. Give Goddramon my regards!"
    ),
    (2,23,51): (
        "Give Goddramon my regards! Ah, this is most acceptable. Thoroughly acceptable!"
    ),
    (2,23,52): (
        "A flower the color of passion? Of course I have one. But I won't hand it over. "
        "If you want it, seize it with your own passion!"
    ),
    (2,23,53): (
        "Your passion came through loud and clear. So I'll give you this Passion Flower... personally."
    ),
    (2,23,54): (
        "Let me teach you one important thing: if you're going to show passion, never get embarrassed. "
        "If you can't manage that, don't even start."
    ),
    (2,23,55): (
        "A flower with a sexy color? You're a little young for that. "
        "If you really want it, take it with your own strength."
    ),
    (2,23,56): (
        "Hmm... You're pretty good. I'll share this Sexy Flower with you."
    ),
    (2,23,57): (
        "I thought you were just a kid, but that flower suits you surprisingly well."
    ),
    (2,23,58): (
        "I wanna form a visual-kei band! I'm understated and cool, so I'll play bass. "
        "Find me a vocalist, drummer, and guitarist! Stealth Valley is the classic place to recruit bandmates!"
    ),
    (2,23,59): (
        "Recruiting for a visual-kei band! Need vocals, drums, and guitar! "
        "Let's find them in Stealth Valley!"
    ),
    (2,23,60): (
        "I said visual-kei, so what is this?! What kind of hilarious, surreal, funky comedy band did we make? "
        "Eh, maybe this can work too! Hey, you! Take your reward!"
    ),
    (2,23,61): "Come to our live show! Thank you very much!",
    (2,23,62): (
        "You're recruiting for a visual-kei band?! Leave the vocals to me! "
        "No, I'm the only possible choice! Anyone else is unthinkable!"
    ),
    (2,23,63): (
        "I'll unleash my burning heat, beat, shouts, and sheer loudness! "
        "My voice will scorch itself into your heart!"
    ),
    (2,23,64): (
        "Visual what? Never heard of it, but leave the drums to me! "
        "No doubt about it - trust me to make a huge boom!"
    ),
    (2,23,65): "And a boom-ba-boom! Ba-boom! Boom-ba-boom! Ba-boom!",
    (2,23,66): (
        "A soaking-wet member who can play guitar? Who else could ya possibly pick but me? "
        "I can also play harmonica, castanets, accordion, trumpet, and tambourine!"
    ),
    (2,23,67): (
        "I can play guitar while blowing a horn and oboe! "
        "Heck, I can balance on a ball at the same time!"
    ),
    (2,23,68): (
        "All my subjects suddenly vanished. They disappeared at Crystal Volcano, "
        "where they were building our Game Kingdom. Could you please find them?"
    ),
    (2,23,69): (
        "My subjects disappeared at Crystal Volcano while building our Game Kingdom. "
        "None have returned, and I'm terribly worried."
    ),
    (2,23,70): (
        "Everyone made it back! Thank you very much. Please accept this modest reward."
    ),
    (2,23,71): (
        "Once the Game Kingdom is finished, I'll invite you too. Until then, farewell!"
    ),
    (2,23,72): (
        "You came looking for us, chess? Thank goodness! The heat nearly knocked me out. "
        "I'm okay now, so please help the others. Just point me toward home, and I can return alone!"
    ),
    (2,23,73): (
        "The Game Kingdom has been our dream for years, chess. "
        "I got so absorbed that I didn't notice myself getting dizzy. I'll be more careful."
    ),
    (2,23,74): (
        "KingChessmon worried and sent you for me? Thank you. I'll return to him immediately. "
        "Let's see... He's in the Front Room."
    ),
    (2,23,75): (
        "You may have saved my life by calling out to me. I got so absorbed that I lost track of time. "
        "I might have collapsed if I'd stayed here any longer."
    ),
    (2,23,76): (
        "KingChessmon sent you to find us?! You're too late! BishopChessmon and QueenChessmon already... "
        "No, they're probably fine. They thought the missing king had been kidnapped, "
        "got furious, and charged into Lost Space. Hurry before they do something terrible!"
    ),
    (2,23,77): (
        "Why Lost Space? They said anything lost in a Zone falls there. "
        "That's not quite how it works? Never mind - please hurry after them!"
    ),
    (2,23,78): (
        "You came searching for a subject? Insolent fool! I serve only one master, "
        "and I will never become yours!"
    ),
    (2,23,79): (
        "My master sent you to retrieve me? Then I have gravely misunderstood. "
        "Please accept my deepest apology."
    ),
    (2,23,80): "I shall return to my master. Farewell.",
    (2,23,81): (
        "You know where KingChessmon is? Very well. I shall force that answer from you! "
        "No more discussion!"
    ),
    (2,23,82): (
        "KingChessmon sent you to find me? ...Then I have treated you terribly. "
        "I am forever rushing to conclusions, and the king always scolds me for it."
    ),
    (2,23,83): (
        "You helped us, and I caused you great trouble. Everything we did came from our devotion to the king. "
        "Please forgive us."
    ),
    (2,23,84): (
        "Taiki, please help! Sakuyamon has been acting strangely. She spends all her time in Lost Space, "
        "chasing weird Digimon, chanting spells, and collecting strange machines, items, and medicine. "
        "I've always looked up to her. Please bring the real Sakuyamon back!"
    ),
    (2,23,85): (
        "Find out what Sakuyamon is doing in Lost Space and bring back the kind Sakuyamon I know!"
    ),
    (2,23,86): (
        "Thank you, Taiki! How was Sakuyamon? ...It's a secret? What kind of secret?! "
        "You investigated and solved her problem, but she says children can't know? "
        "I'm not a child! And if I am, then so are you! What is that supposed to mean?! Grrr!"
    ),
    (2,23,87): (
        "Thank you for investigating Sakuyamon and bringing her back to normal. "
        "I'm grateful from the bottom of my heart. ...But right now, I absolutely hate you, Taiki!"
    ),
    (2,23,88): (
        "Bring me back to normal? What does that mean? I haven't changed. "
        "I'm the same pretty shrine-maiden Digimon who carries the will of the gods! "
        "Why are you making that disgusted face?! Now you'll receive some personal divine punishment!"
    ),
    (2,23,89): (
        "Renamon asked you to come? Hmm? Every single one of her worries is imaginary."
    ),
    (2,23,90): (
        "Well, I'll be going now. Don't follow just because you can't leave me alone. "
        "I'm heading into Lost Space for... a date with Apocalymon!"
    ),
    (2,23,91): (
        "What?! You defeated Apocalymon?! You weren't supposed to do that! "
        "I was so close! Now you'll receive some personal divine punishment!"
    ),
    (2,23,92): (
        "Fine, listen carefully. Apocalymon feeds on negative emotions: anger, sadness, hatred, envy, fear, "
        "and all those ugly feelings. I found him collapsed and tried machines, medicine, spells - everything. "
        "Nothing worked, and he kept weakening. Then I happened to unleash my anger at him, "
        "and suddenly he began recovering! Look, Taiki. Didn't he grow up splendidly?"
    ),
    (2,23,93): (
        "Little Apocalymon finally left the nest, so all's well that ends well! "
        "It wasn't the plan, but the result worked out. Keep this secret from Renamon, Taiki. "
        "She's still a child, so she shouldn't know."
    ),
    (2,23,94): (
        "Who are you? You came to defeat me? Ha ha ha! Interesting! "
        "This Zone is full of fools who deliver themselves to me as food!"
    ),
    (2,23,95): (
        "Set Sakuyamon free? What are you talking about? I'm the one sick of her! "
        "She keeps barging in and starting fights. Usually she speaks and acts like a complete airhead, "
        "but here she attacks with incredible anger and hatred. I have no idea why she'd stalk and resent me... "
        "Wait a moment."
    ),
    (2,23,96): (
        "...Listen. Go back and tell Sakuyamon never to come here again. "
        "I'm disappearing. I will never see her again."
    ),
    (2,23,97): (
        "The bird on my right arm is Freyja. I want an equally radiant bird on my left! "
        "Preferably someone intelligent and useful. Could you recruit one? "
        "Rumor says there's an amazing bird in Papyrus Desert."
    ),
    (2,23,98): (
        "Find me an intelligent, useful bird who shines brilliantly!"
    ),
    (2,23,99): (
        "You recruited my bird? Great, here's your reward. Wait, what did you say? Z-Zhuqiaomon?! "
        "What have you done?! Is he intelligent and useful? Far more than I am! Radiant? "
        "He's so bright I'm dizzy! My arm will burn, and then the rest of me will be roasted too!"
    ),
    (2,23,100): (
        "Of course I'm satisfied and grateful. But if I get burned to a crisp, "
        "I'm sending him to live with you next."
    ),
    (2,23,101): (
        "An intelligent, useful, radiant bird? I certainly shine, but if you need intelligence too, "
        "only one Digimon fits. Yes, that great one at Skull Glacier!"
    ),
    (2,23,102): (
        "I recommend that great Digimon at Skull Glacier. Someone like me isn't remotely worthy... right?"
    ),
    (2,23,103): (
        "No, there's a far more impressive bird than me! You should absolutely choose him. "
        "The perfect bird is at Crystal Volcano."
    ),
    (2,23,104): (
        "Considering your requirements, only that bird at Crystal Volcano could possibly fit!"
    ),
    (2,23,105): (
        "...I understand your request. All that remains is testing whether you are worthy to be my master."
    ),
    (2,23,106): (
        "I recognize you as a worthy master. Hmm? You aren't the one? "
        "If you vouch for this other Digimon, I have no objection. I will meet him, if he agrees."
    ),
    (2,23,107): (
        "He wants me perched on his arm? Very well. I only hope he takes care not to burn himself."
    ),
    (2,23,108): (
        "We're playing Calumon's original hide-and-seek game, Getcha Calumon! "
        "It doesn't end until you catch all fourteen Calumon. Of course you're 'it,' Taiki! "
        "Catch lots and lots of us, calu!"
    ),
    (2,23,109): (
        "Catch Calumon hiding all over the place. There are fourteen of us, so get them all, calu!"
    ),
    (2,23,110): (
        "You did it, calu! That's Taiki for you! But one final Calumon is hiding in Skyfort. "
        "Find that one and you'll really be finished!"
    ),
    (2,23,111): (
        "Thank you so much, calu! Please accept Calumon's reward!"
    ),
    (2,23,112): (
        "One last thing! If you find me somewhere afterward, I'll join your team anytime, calu!"
    ),
    (2,23,113): _CALUMON_FOUND,
    (2,23,114): (
        "You already found me, Taiki. Looking back at what's finished won't move you forward, calu!"
    ),
    (2,23,115): _CALUMON_FOUND,
    (2,23,116): (
        "You already found me, Taiki. Still, being found again makes me a little happy, calu!"
    ),
    (2,23,117): _CALUMON_FOUND,
    (2,23,118): (
        "You already found me, Taiki. If you find me again, I'll go back to my parents' house, calu!"
    ),
    (2,23,119): _CALUMON_FOUND,
    (2,23,120): (
        "You already found me, Taiki. I'm only standing here to trick you, calu!"
    ),
    (2,23,121): _CALUMON_FOUND,
    (2,23,122): (
        "You already found me, Taiki. Being found is even more exciting than finding someone, calu!"
    ),
    (2,23,123): _CALUMON_FOUND,
    (2,23,124): (
        "You already found me, Taiki. I'm still happy every time you find me, calu!"
    ),
    (2,23,125): _CALUMON_FOUND,
    (2,23,126): (
        "You already found me, Taiki. But you'd never tell me to go away. That's just like you, calu!"
    ),
})
del _CALUMON_FOUND

# Batch 3U: Apocalymon's rematch and both DigiFarm personality sets.
_CALUMON_FOUND_AGAIN = "Aww, you found me! You got me, calu!"
OVERRIDES.update({
    (2,23,127): _CALUMON_FOUND_AGAIN,
    (2,23,128): (
        "You already found me, Taiki. At least that's what this event flag says, calu!"
    ),
    (2,23,129): _CALUMON_FOUND_AGAIN,
    (2,23,130): (
        "You already found me, Taiki. If you want to talk that badly, come find me as often as you like!"
    ),
    (2,23,131): _CALUMON_FOUND_AGAIN,
    (2,23,132): (
        "You already found me, Taiki. We're hard to tell apart, but you really did find me, calu!"
    ),
    (2,23,133): _CALUMON_FOUND_AGAIN,
    (2,23,134): (
        "You already found me, Taiki. The only thing worth rediscovering over and over "
        "is a bittersweet memory, calu!"
    ),
    (2,23,135): _CALUMON_FOUND_AGAIN,
    (2,23,136): (
        "You already found me, Taiki. And now all of us have found you too, calu!"
    ),
    (2,23,137): _CALUMON_FOUND_AGAIN,
    (2,23,138): (
        "You already found me, Taiki. The moment you think you'll never find something "
        "is exactly when you should look, calu!"
    ),
    (2,23,139): _CALUMON_FOUND_AGAIN,
    (2,23,140): (
        "You already found me, Taiki. Disappointed? Don't worry! "
        "Even when your heart nearly breaks, your feet can keep moving forward, calu!"
    ),
    (2,23,141): (
        "Aww, you found me! You got me, calu! And you caught the final Calumon!"
    ),
    (2,23,142): (
        "You already found me, Taiki. Return to the Front Room and collect your reward, calu!"
    ),
    (2,23,143): (
        "Apocalymon is apparently trying to destroy the wall around this Zone. "
        "I have no idea what he's thinking, but we can't ignore him. Will you stop him?"
    ),
    (2,23,144): (
        "We don't know where Apocalymon is now, but the damage was reported at Crystal Volcano. "
        "Question the Digimon there."
    ),
    (2,23,145): (
        "Thank you for stopping Apocalymon. Please take this reward; you truly saved us. "
        "Still, I couldn't understand your explanation at all. What was Apocalymon trying to accomplish?"
    ),
    (2,23,146): (
        "He realized he loved someone he'd always hated, but their difference in status made it impossible, "
        "so he snapped? Sorry, now I understand even less. Are you truly talking about Apocalymon? "
        "I can't even imagine it."
    ),
    (2,23,147): (
        "You came to stop Apocalymon? Thank goodness. He's raging about smashing everything "
        "and erasing the world. I don't know what happened, but stop him before he does something catastrophic. "
        "He entered Crystal Cave."
    ),
    (2,23,148): (
        "Apocalymon probably went into Crystal Cave. He was furious, so be careful."
    ),
    (2,23,149): (
        "Looking for Apocalymon? He's at Crystal Mine. You'll probably go no matter what I say, "
        "but I advise against it. Apparently you're the reason he's raging."
    ),
    (2,23,150): (
        "Apocalymon is at Crystal Mine. He's probably waiting there for you."
    ),
    (2,23,151): (
        "I never thought you'd actually appear. What a fool. Did you think you could beat me again? "
        "If you expect the same opponent as last time, you're badly mistaken!"
    ),
    (2,23,152): (
        "Hmph. Did you think that was the end? It was only a test - a warm-up. "
        "Now our real battle begins!"
    ),
    (2,23,153): (
        "...I lost. I truly thought I'd win this time. She made me this strong, "
        "and now I can't face her. Then again, even if I'd beaten you, I still couldn't face her..."
    ),
    (2,23,154): (
        "I always thought Sakuyamon was an annoying fool who kept attacking despite being weak. "
        "Now I understand: she was holding back. When I was fading away, "
        "she trained me little by little and restored enough strength for me to survive alone. "
        "...I could never measure up to her."
    ),
    (2,23,155): (
        "I'm a ^0-type, ^1-species Digimon: ^2!\n\n"
        "I'm thrilled to be on this Farm Island! I'll train hard and get strong fast!"
    ),
    (2,23,156): (
        "Here's a question Taiki should answer easily: what is the weapon Neptunemon carries?"
    ),
    (2,23,157): "King's Bite",
    (2,23,158): "Viking Strike",
    (2,23,159): (
        "Correct! King's Bite is Neptunemon's living spear. "
        "Of course Taiki would know that!"
    ),
    (2,23,160): (
        "Bzzzzt! There's no weapon named after a pirate strike! Are you really Taiki? "
        "Is Pickmon hiding inside you?"
    ),
    (2,23,161): (
        "Here's an easy one for Taiki! Is Shoutmon's home the Village of Smiles or Sunlit Forest?"
    ),
    (2,23,162): "Village of Smiles",
    (2,23,163): "Sunlit Forest",
    (2,23,164): (
        "Correct! If you missed that, you couldn't be Taiki - just some Taiki-shaped impostor!"
    ),
    (2,23,165): (
        "No! Now I know you aren't Taiki. Taiki could never miss that! "
        "Maybe you're Tanuki, Taiko, or Takenoko, but you're definitely a fake!"
    ),
    (2,23,166): (
        "Nobody else in the Digital World might know this, but Taiki will: "
        "how many children are in Akari's family?"
    ),
    (2,23,167): "Four siblings",
    (2,23,168): "She's an only child",
    (2,23,169): (
        "Correct! Naturally. Akari has three younger brothers, so she's the dependable oldest of four! "
        "I've never met those brothers, though!"
    ),
    (2,23,170): (
        "That's you, Taiki! You're an only child, but Akari has three younger brothers, "
        "so there are four siblings! You're Fake Taiki, aren't you?! I'll tear off that disguise!"
    ),
    (2,23,171): (
        "This is so easy Taiki will yawn: what does Cutemon hate most?"
    ),
    (2,23,172): "Tears of sadness",
    (2,23,173): "An empty stomach",
    (2,23,174): (
        "Correct, correct, CORRECT! Though Cutemon cries quite a bit for someone who hates tears... "
        "Eh, never mind!"
    ),
    (2,23,175): (
        "Wrong, wrong, WRONG! Personally, that's a fair answer, but the quiz says no! "
        "Hold your head high even when you're hungry. Deal with it!"
    ),
    (2,23,176): (
        "Just between us, here's my real concern: how long can I keep going on momentum alone?"
    ),
    (2,23,177): "Forever!",
    (2,23,178): "You can't even now",
    (2,23,179): (
        "I can keep going? Can I...? No, I can't hesitate! "
        "I have to charge forward at full speed without looking back! "
        "Wait, is that actually a positive attitude?"
    ),
    (2,23,180): (
        "Ha ha! I can't hear you, Taiki! All that matters is momentum, spirit, and blind confidence! "
        "Run faster than your feet sink and you can cross water! "
        "First, you have to fool yourself into believing it!"
    ),
    (2,23,181): (
        "You've played this game for ^0 hours and ^1 minutes so far! "
        "We're only getting started, so let's keep charging ahead!"
    ),
    (2,23,182): (
        "Every Digimon has an attribute weakness! For example, Mythical Beast Digimon are weak to Dark. "
        "If you ignore matchups, you'll lose!"
    ),
    (2,23,183): (
        "Every Digimon also has an attribute strength! For example, Beast Digimon resist Fighting. "
        "Use matchups well and battles become easy!"
    ),
    (2,23,184): (
        "My field skill is Rock Smash! I can shatter any boulder blocking the road in one hit!"
    ),
    (2,23,185): (
        "My field skill is Melt Ice! I can cleanly melt any ice blocking the road!"
    ),
    (2,23,186): (
        "My field skill is Tree Cut! I can slice down any huge tree blocking the road!"
    ),
    (2,23,187): (
        "My field skill is Dig! I can use underground tunnels to reach other places!"
    ),
    (2,23,188): (
        "My field skill is Dive! I can use underwater passages to reach other places!"
    ),
    (2,23,189): (
        "I don't have a field skill, and I don't need one! I'll make up for it by fighting harder than anyone!"
    ),
    (2,23,190): (
        "This new Farm Good seems to affect our HP and MP! I can't wait to see how much it helps!"
    ),
    (2,23,191): (
        "This new Farm Good seems to affect our EXP! I can't wait to see how much faster it grows!"
    ),
    (2,23,192): (
        "This new Farm Good seems to affect our Attack! I'm excited to see how much it changes!"
    ),
    (2,23,193): (
        "This new Farm Good seems to affect our Spirit! I can't wait to see how much smarter we get!"
    ),
    (2,23,194): (
        "This new Farm Good seems to affect our Speed! It'll be fun seeing how fast we become!"
    ),
    (2,23,195): (
        "This new Farm Good seems to affect our Defense! I can't wait to see how tough we become!"
    ),
    (2,23,196): (
        "This new Farm Good seems useful for making equipment! I can't wait to see what we can create!"
    ),
    (2,23,197): (
        "We need Farm Goods to become stronger. Come on, Taiki - place some for us!"
    ),
    (2,23,198): (
        "Do you like training, Taiki? I love it! Nothing beats that feeling of 'Look how hard I'm working!' "
        "Results? Who cares about those?"
    ),
    (2,23,199): (
        "What do I like? Myself, of course! I absolutely love being me! "
        "Hey, don't back away! Come back!"
    ),
    (2,24,0): (
        "What do I hate? Being ignored! Especially when I have a microphone. "
        "If someone tunes me out, I lose it!"
    ),
    (2,24,1): (
        "Do I ever feel down? Of course! I'm sensitive! What do I do about it? Nothing. "
        "By the next time I notice, I'm already fine!"
    ),
    (2,24,2): (
        "Someone said my singing was too loud. I was really getting into the groove, too... "
        "That's just not faaaair!"
    ),
    (2,24,3): (
        "I tried blowing out a candle with a fiery shout, but inhaled by mistake and burned my mouth. "
        "I know I did something wrong. I'm just no longer sure which part was wrong."
    ),
    (2,24,4): (
        "WOOOAH-WOAH-WOOOAH! My shout put you in a trance, huh? "
        "Your eyes rolled back for a second. Wait... Did you pass out?"
    ),
    (2,24,5): (
        "Listen to my shout! You don't want to? Fine, then I'll listen to your passionate shout first. "
        "You don't want that either?! Stop being so picky!"
    ),
    (2,24,6): (
        "Listen! I finally did it! I started by shattering glass cups with my voice, "
        "and now I can crack Chrome Digizoid! Hey, why are you running? Listen to me!"
    ),
    (2,24,7): (
        "Taiki, it's boring here! Put me in the party and let me fight something huge! Come on, please!"
    ),
    (2,24,8): "Huh? Can I stop working now?",
    (2,24,9): "Got it! Just tell me anytime!",
    (2,24,10): "Got it! I'll return to work!",
    (2,24,11): "You have a job for me? I'm ready anytime!",
    (2,24,12): (
        "Whoa, delicious! This is amazing! I can feel power surging through me!"
    ),
    (2,24,13): "Thanks for the DigiNoir! I feel much better.",
    (2,24,14): "...Huh? It doesn't taste very good to me right now.",
    (2,24,15): "Sorry, but I'm full right now.",
    (2,24,16): (
        "I'm a ^0-type, ^1-species Digimon: ^2!\n\n"
        "I'm so happy to be on this Farm Island! I'll train hard and keep getting stronger!"
    ),
    (2,24,17): (
        "Hey, Taiki, answer this: what's the one thing Mammothmon can't handle?"
    ),
    (2,24,18): "Heat!",
    (2,24,19): "Cold!",
    (2,24,20): (
        "Correct! Heat is the one thing it can't stand. Wasn't Mammothmon buried in ice for ages? "
        "I couldn't endure that myself!"
    ),
    (2,24,21): (
        "Wrong! Completely wrong! Taiki, how can you miss something this easy? "
        "I'm seriously disappointed. Boo!"
    ),
    (2,24,22): (
        "Quick, Taiki: which one can't fly, Biyomon or Patamon?"
    ),
    (2,24,23): "Both can fly!",
    (2,24,24): "Neither can fly!",
    (2,24,25): (
        "Correct! Nice work, Taiki! It was a trick question, but you cleared it easily. "
        "Between us, they're both so slow that calling it 'flying' is generous."
    ),
    (2,24,26): (
        "Bzzzzt! Wrong! You tried to outsmart the trick and got caught. "
        "Then again, both fly slower than they walk, so you could argue they're merely floating."
    ),
    (2,24,27): (
        "Answer right now, Taiki: what is WarGreymon's armor made from?"
    ),
    (2,24,28): "Chrome Digizoid",
    (2,24,29): "Calcium",
    (2,24,30): (
        "Ding ding ding! Correct! But if you'd called it Chrome Digizoid Metal, I'd have buzzed you!"
    ),
    (2,24,31): (
        "Right, calcium. Sure... As if! I'm not just disappointed by the answer; "
        "I'm disappointed you thought that joke would land!"
    ),
    (2,24,32): (
        "Hey, Taiki, tell me: what is MarineAngemon's signature move?"
    ),
    (2,24,33): "Ocean Love",
    (2,24,34): "Holy Flame",
    (2,24,35): (
        "Yay, correct! That's Taiki for you! I feel like Ocean Love hit me - "
        "my eyes are about to turn into hearts!"
    ),
    (2,24,36): (
        "Bzzzzzzzt! A longer buzz than usual! That's another Digimon's signature move. "
        "I won't tell you whose!"
    ),
})
del _CALUMON_FOUND_AGAIN

# Batch 3V: additional DigiFarm voices, quizzes, work prompts, and system tips.
OVERRIDES.update({
    (2,24,37): (
        "Hey, Taiki? When you choose a partner Digimon, what matters most to you?"
    ),
    (2,24,38): "Their heart",
    (2,24,39): "Their looks",
    (2,24,40): (
        "Oh, really? Hmm... I see. That's what I expected. Hee hee hee!"
    ),
    (2,24,41): (
        "What?! ...Well, looks do matter a little, but hearing you say it that bluntly is kind of a shock."
    ),
    (2,24,42): (
        "You've played this game for ^0 hours and ^1 minutes so far. "
        "Let's keep adventuring together!"
    ),
    (2,24,43): (
        "Every Digimon has an attribute weakness. For example, Mythical Beast Digimon are weak to Dark. "
        "If you ignore matchups, you could lose!"
    ),
    (2,24,44): (
        "Every Digimon has an attribute strength too. For example, Beast Digimon resist Fighting. "
        "Use matchups well and battles become much easier!"
    ),
    (2,24,45): (
        "My field skill is Rock Smash. I can break apart boulders blocking the road!"
    ),
    (2,24,46): (
        "My field skill is Melt Ice. I can cleanly melt ice blocking the road!"
    ),
    (2,24,47): (
        "My field skill is Tree Cut. I can slice down huge trees blocking the road!"
    ),
    (2,24,48): (
        "My field skill is Dig. I can use underground tunnels to reach other places!"
    ),
    (2,24,49): (
        "My field skill is Dive. I can use underwater passages to reach other places!"
    ),
    (2,24,50): (
        "I don't have a field skill, but I'll make up for it by fighting hard!"
    ),
    (2,24,51): (
        "The new Farm Good you placed seems to affect our HP and MP. I can't wait to see how it helps!"
    ),
    (2,24,52): (
        "The new Farm Good you placed seems to affect our EXP. I can't wait to see how it helps!"
    ),
    (2,24,53): (
        "The new Farm Good you placed seems to affect our Attack. I can't wait to see how it helps!"
    ),
    (2,24,54): (
        "The new Farm Good you placed seems to affect our Spirit. I can't wait to see how it helps!"
    ),
    (2,24,55): (
        "The new Farm Good you placed seems to affect our Speed. I can't wait to see how it helps!"
    ),
    (2,24,56): (
        "The new Farm Good you placed seems to affect our Defense. I can't wait to see how it helps!"
    ),
    (2,24,57): (
        "The new Farm Good you placed seems necessary for making equipment. "
        "I can't wait to see what we can create!"
    ),
    (2,24,58): (
        "We need Farm Goods to become stronger. Please place some for us, Taiki!"
    ),
    (2,24,59): (
        "Um, Taiki? Are those goggles and gloves supposed to make some kind of statement? "
        "They're the mark of the protagonist? Oh. Then I'll just ignore that!"
    ),
    (2,24,60): (
        "Why ask what I like? My favorites change constantly, and I forget what I said before anyway. "
        "Right now... let's say my favorite is Taiki!"
    ),
    (2,24,61): (
        "What do I hate? People who are always negative. I want to find fun and beauty wherever I can. "
        "I can't stand annoying people who make everyone feel miserable!"
    ),
    (2,24,62): (
        "Taiki, don't people ever call you fickle? Why am I the only one who always gets called that? "
        "They do call you that? Because, look... Actually, never mind."
    ),
    (2,24,63): (
        "Hmm? I'm extremely busy right now. Can't you tell? I'm about to take a nap. "
        "We'll play another time!"
    ),
    (2,24,64): (
        "Someone once asked what it feels like to be a cool character. That's impossible to answer. "
        "I've been cool since birth, so I don't understand how uncool people feel. "
        "What was that snort?! Why is your nose running? Hey!"
    ),
    (2,24,65): (
        "Hmm-hmm-hmmm! I'm not especially cheerful. Why am I humming? "
        "Because I can't remember the lyrics! Hmm-hmm-hmmm!"
    ),
    (2,24,66): (
        "I call myself a Digimon, but my funny looks and speech don't feel very digital. "
        "Maybe I need an edgy makeover and more technical-sounding words. Ballistamon? "
        "That's not what I mean! He's incredibly analog - and he's a robot!"
    ),
    (2,24,67): (
        "When are you happiest, Taiki? For me, it's that moment before sleep when consciousness fades. "
        "But fighting at the front of my friends makes me just as happy. "
        "I love feeling every unnecessary thought melt away."
    ),
    (2,24,68): "Taiki, I'm bored with the DigiFarm. Let's go somewhere already!",
    (2,24,69): "Huh? Can I stop working now?",
    (2,24,70): "Okay! Call me anytime.",
    (2,24,71): "All right, I'll get back to work!",
    (2,24,72): "Hmm? Do you have a job for me?",
    (2,24,73): "Mmm, delicious! DigiNoir really is the best!",
    (2,24,74): "Yay, DigiNoir! I feel a little better!",
    (2,24,75): "Hmm... Eating isn't making me feel much better right now.",
    (2,24,76): "Sorry, I'm full right now.",
    (2,24,77): (
        "I'm a ^0-type, ^1-species Digimon: ^2!\n\n"
        "I came all the way to this Farm Island! Train me hard, and I'll smash everyone in sight!"
    ),
    (2,24,78): (
        "Hey, Taiki! Quiz time! Omnimon uses Supreme Cannon and Transcendent Sword. "
        "Which attack comes from his right arm?"
    ),
    (2,24,79): "Supreme Cannon",
    (2,24,80): "Transcendent Sword",
    (2,24,81): (
        "Correct! That's Taiki for you! Supreme Cannon fires from Omnimon's right arm, "
        "launching a brutally cold blast!"
    ),
    (2,24,82): (
        "Wrong! That's his left arm! Transcendent Sword extends from Omnimon's left arm. "
        "I asked about the right!"
    ),
    (2,24,83): (
        "Hey, Taiki! Answer this: what is Ikkakumon's sharp horn made from?"
    ),
    (2,24,84): "Mithril",
    (2,24,85): "Mystery",
    (2,24,86): (
        "Correct! Apparently, it's made from mithril. I didn't shave off a sample to check, "
        "so that's only a rumor, but it felt incredibly hard!"
    ),
    (2,24,87): (
        "Right, it's packed with mystery... No! That's your head! "
        "The horn is made from mithril - the extremely hard stuff!"
    ),
    (2,24,88): (
        "Here's a question, Taiki, and missing it would be a huge problem: "
        "what is your friend Ballistamon's signature move?"
    ),
    (2,24,89): "Heavy Speaker",
    (2,24,90): "Heavy Waiter",
    (2,24,91): (
        "Correct! Obviously! If Taiki had missed that, Ballistamon could use Heavy Speaker to boo him!"
    ),
    (2,24,92): (
        "Wrong! Sure, Ballistamon is heavy, but not knowing his signature move is impossible! "
        "Even as a joke, that answer was terrible!"
    ),
    (2,24,93): (
        "Answer this one, Taiki: what does the mummy Mummymon always carry under his arm?"
    ),
    (2,24,94): "Obelisk",
    (2,24,95): "A crutch",
    (2,24,96): (
        "Correct! Mummymon carries his favorite gun, Obelisk!"
    ),
    (2,24,97): (
        "Wrong! That's his gun, Obelisk. It resembles a crutch, but come on - "
        "being bandaged head to toe and having broken bones would be too much!"
    ),
    (2,24,98): (
        "Hey, Taiki! When choosing a partner Digimon, what matters to you?"
    ),
    (2,24,99): "Hot-blooded spirit",
    (2,24,100): "Cool composure",
    (2,24,101): (
        "Exactly! Battle demands a blazing, passionate heart! I knew you'd understand!"
    ),
    (2,24,102): (
        "What?! You'd choose someone cold to fight beside you? "
        "Your hearts and bodies would both freeze solid!"
    ),
    (2,24,103): (
        "You've played this game for ^0 hours and ^1 minutes! "
        "Let's keep going together forever!"
    ),
    (2,24,104): (
        "Every Digimon has an attribute weakness! For example, Aquatic Digimon are weak to Lightning. "
        "Matchups are crucial in battle!"
    ),
    (2,24,105): (
        "Every Digimon has an attribute strength! For example, Machine Digimon resist Fire. "
        "Matchups are crucial in battle!"
    ),
    (2,24,106): (
        "I have the Rock Smash field skill! I'll crush any boulder blocking the road!"
    ),
    (2,24,107): (
        "I have the Melt Ice field skill! I'll melt any ice blocking the road!"
    ),
    (2,24,108): (
        "I have the Tree Cut field skill! I'll slice down any huge tree blocking the road!"
    ),
    (2,24,109): (
        "I have the Dig field skill! We can take underground shortcuts to other places. "
        "Digging makes the quickest route!"
    ),
    (2,24,110): (
        "I have the Dive field skill! We can use underwater passages to reach other places. "
        "You don't even need to know how to swim!"
    ),
    (2,24,111): (
        "I don't have a field skill! I'll make up for it with pure fighting spirit!"
    ),
    (2,24,112): (
        "The new Farm Good seems to affect our HP and MP! I can't wait to see how it helps!"
    ),
    (2,24,113): (
        "The new Farm Good seems to affect our EXP! I can't wait to see how it helps!"
    ),
    (2,24,114): (
        "The new Farm Good seems to affect our Attack! I can't wait to see how it helps!"
    ),
    (2,24,115): (
        "The new Farm Good seems to affect our Spirit! I can't wait to see how it helps!"
    ),
    (2,24,116): (
        "The new Farm Good seems to affect our Speed! I can't wait to see how it helps!"
    ),
    (2,24,117): (
        "The new Farm Good seems to affect our Defense! I can't wait to see how it helps!"
    ),
    (2,24,118): (
        "The new Farm Good seems useful for making equipment! I can't wait to see what we can create!"
    ),
    (2,24,119): (
        "We need Farm Goods to get stronger! If you want to train us, place some already!"
    ),
    (2,24,120): (
        "Sometimes an opponent seems to move in slow motion during battle. "
        "At first I thought that meant I was amazing, but looking back, I was moving slowly too. "
        "So it didn't help at all. Is that only me? Oh... only me."
    ),
    (2,24,121): (
        "What do I like? That's obvious: thrilling battles and adventures! "
        "That's how a Digimon should live!"
    ),
    (2,24,122): (
        "What do I hate? Occult stuff. If I can punch it and settle the problem, fine. "
        "But curses and other nonsense clinging to me? No way. I want problems that go BOOM!"
    ),
    (2,24,123): (
        "Someone asked how to become a wild type. Why ask me? "
        "Choosing it as a goal and asking for advice already isn't wild. "
        "More importantly, I thought I was the cheerful type. What do you think?"
    ),
    (2,24,124): (
        "Taiki, this is a disaster! The most terrifying group in this Zone, Team Cute, is reforming! "
        "Only their victims understand the pain. They reject you by standards nobody understands, "
        "then smile while giving you a horrifying nickname! I don't want that!"
    ),
    (2,24,125): (
        "Hmm... My mind and body both feel rusty lately. Especially my mind. "
        "My energy is way too low! RAAAAAH!"
    ),
    (2,24,126): (
        "Taiki, remember this! When your energy is low, don't wait for it to rise. "
        "Energy doesn't rise on its own - you raise it! Grab happiness yourself! "
        "Attack first! Shout from your stomach! Got it?!"
    ),
    (2,24,127): (
        "Taiki, here's simple but important advice: strike when the enemy starts or finishes an action. "
        "Those moments often leave them unguarded. Protect yourself at those times too! "
        "Why the blank stare? It's strange hearing me get serious? I'm always one hundred percent serious!"
    ),
    (2,24,128): (
        "People think I'm angry because of my personality, but I'm usually just excited. "
        "I've only truly snapped once: when someone squeezed DigiLemon onto my Digi-fried chicken without asking. "
        "Even someone as calm as me can't forgive that!"
    ),
})

# Batch 3W: global story records 4929-5080.
_BATCH_3W = {
    4929: (
        "Wooo! Taiki! I'm bored out of my mind! Take me somewhere! Come on, please! "
        "I need a thrilling, action-packed adventure!"
    ),
    4930: "Huh?! Is it really okay to stop working?",
    4931: "All right! I've still got plenty of energy, but I'll take a quick break!",
    4932: "Yeah! I'll work my tail off and crank out a ton of stuff!",
    4933: "Huh?! What is it? You got a job for me?",
    4934: "Whoa, this is seriously good! I can feel the power surging through me!",
    4935: "Man, that hit the spot! I was starving. I'm feeling better already!",
    4936: "Hmm... This really isn't my kind of flavor!",
    4937: "I'm not hungry right now. Ask me again later!",
    4938: (
        "I am ^2, a ^0-type, ^1-species Digimon. Perhaps fate brought me here. "
        "While I remain, I intend to train hard and prove my strength."
    ),
    4939: "One question, Taiki. Where do Wizardmon and Witchmon come from?",
    4940: "Witchelny",
    4941: "Nerima",
    4942: (
        "Correct, Taiki. They are said to come from Witchelny, a Digital World in another dimension. "
        "I don't know the details, and frankly, I don't care to."
    ),
    4943: (
        "How should I put this? You're wrong, Taiki. Not only about the answer, but perhaps about your "
        "entire approach to life. Still, I can't say I dislike that about you."
    ),
    4944: "Question, Taiki. ShogunGekomon uses its voice as a weapon. What is its signature move?",
    4945: "Kobushi Tone",
    4946: "Geko Geko Horn",
    4947: "Correct. Well done. No punch line this time.",
    4948: (
        "The answer that resembles the Digimon's name looked more convincing, didn't it? "
        "It was a trick question, though not a very inspired one. We both chose poorly today, Taiki."
    ),
    4949: "Quick question, Taiki. What hardened to form the drill on Dorulumon's forehead?",
    4950: "Its hair",
    4951: "Its skull",
    4952: (
        "Correct. You look far too pleased about guessing the joke answer, Taiki. Even I have trouble "
        "believing it, but reality and plausibility are two different things."
    ),
    4953: (
        "Wrong, Taiki. You know Dorulu Buster, yes? If a piece of skull spun at high speed and launched "
        "from his head, that would normally be fatal. And don't ask why the hair makes any more sense. "
        "That's beyond me."
    ),
    4954: "Answer this, Taiki. What terrifying secret lies inside Garbagemon's trash can?",
    4955: "A black hole",
    4956: "Vintage garbage",
    4957: (
        "Correct, Taiki. They say the inside of that trash can is a black hole, and anything swallowed "
        "by it is gone forever. True or not, I wouldn't recommend testing it."
    ),
    4958: (
        "A plausible answer, but wrong, Taiki. When you're unsure, choose the impossible answer. "
        "Even if you miss, it'll make a better story."
    ),
    4959: "Allow me one personal question. What matters most when you choose a partner Digimon?",
    4960: "Coolness",
    4961: "Passion",
    4962: (
        "I see. A Digimon's ability to remain cool under pressure is vital in battle. "
        "Heh... Thank you, Taiki. That was quite helpful."
    ),
    4963: (
        "Hmm? Do you mean a positive attitude, or the passion to fight beyond one's limits? "
        "Either way, it has little to do with me. Losing my composure would mean losing my pride."
    ),
    4964: (
        "You have played this game for ^0 hours and ^1 minutes so far. Heh... "
        "In the end, numbers are merely numbers."
    ),
    4965: (
        "Every Digimon has an elemental weakness. Bird Digimon, for example, are weak to Lightning. "
        "Think carefully before you fight."
    ),
    4966: (
        "Every Digimon has an elemental resistance. Insect Digimon, for example, resist Lightning. "
        "Plan around those matchups and battle efficiently."
    ),
    4967: "I have the Rock Smash field skill. Bring me along when a boulder blocks your path.",
    4968: "I have the Melt Ice field skill. Bring me along when ice blocks your path.",
    4969: "I have the Tree Cut field skill. Bring me along when a fallen tree blocks your path.",
    4970: "I have the Dig field skill. I can travel underground and reach otherwise inaccessible places.",
    4971: "I have the Dive field skill. I can travel underwater and reach otherwise inaccessible places.",
    4972: "I have no field skill. However, I possess other abilities that more than make up for it.",
    4973: (
        "The new Farm Goods apparently affect our HP and MP. I'm curious to see exactly what they do."
    ),
    4974: "The new Farm Goods apparently affect the EXP we earn. I'm curious to see exactly what they do.",
    4975: "The new Farm Goods apparently affect our Attack. I'm curious to see exactly what they do.",
    4976: "The new Farm Goods apparently affect our Spirit. I'm curious to see exactly what they do.",
    4977: "The new Farm Goods apparently affect our Speed. I'm curious to see exactly what they do.",
    4978: "The new Farm Goods apparently affect our Defense. I'm curious to see exactly what they do.",
    4979: (
        "The new Farm Goods apparently help us create equipment. I'm curious to see what we can make."
    ),
    4980: (
        "Farm Goods can make us stronger. Taiki, give some thought to which ones you should install."
    ),
    4981: (
        "You're quite popular with the other Digimon lately, Taiki. They've even given you secret "
        "nicknames. You haven't heard? 'Stylish Shorts' is rather good. 'Smiling Fashion Goggles' "
        "isn't bad either. Then there's 'Secret Skintight Tights.' Hmm? Why is your face twitching?"
    ),
    4982: "What do I like? Heh... Freedom, I suppose. And DigiNoir. That stuff is delicious.",
    4983: (
        "What do I hate? Nothing in particular. My heart isn't so narrow... "
        "Actually, I hate myself for spouting such shallow, pretty nonsense."
    ),
    4984: (
        "The secret to staying calm? You may regret asking. First, decide that almost nothing in the "
        "world truly matters. Feeling uncomfortable yet? Then always expect the worst and give up in "
        "advance. You'll never panic again. Honestly, though, I wouldn't want to see you become that "
        "kind of person, Taiki."
    ),
    4985: (
        "Taiki, I've been wondering. At the DigiLab, you combine one Digimon with another. "
        "Where does the Digimon that disappears actually go? Huh? 'It lives on in everyone's hearts'? "
        "Don't look so proud of yourself. That isn't the answer I wanted."
    ),
    4986: (
        "Why do Digimon fight? Why would you even ask? The answer is obvious: because we want to. "
        "Most Digimon only do what they truly want to do."
    ),
    4987: (
        "Nuh-nuh-nuh, nuh-nuh-nuh-nuh! Tiddly-dee, tiddly-doo... Gah?! "
        "T-T-T-Taiki?! How long have you been there? From the beginning?! "
        "Tell anyone what you saw or heard, and I'll beat you senseless while sobbing!"
    ),
    4988: (
        "You wonder if I ever get carried away? Heh... Of course not. "
        "Or rather, please just pretend I don't. I'm begging you."
    ),
    4989: (
        "Pray to the gods? Never. There are Digimon who look like gods, remember? "
        "Would you ask those characters for a favor? ...Yes, exactly. "
        "You agreed awfully quickly. Now I have mixed feelings."
    ),
    4990: (
        "Taiki, would you take me somewhere? I don't dislike this farm, but I still long to fight. "
        "We Digimon exist for battle."
    ),
    4991: "Is it really all right for me to stop working?",
    4992: "I see. Then I shall rest for a while.",
    4993: "I see. Then I shall return to work.",
    4994: "Do you want me to begin working?",
    4995: "Remarkable. This DigiNoir is delicious. I can feel strength surging through my entire body.",
    4996: "A rather tasty DigiNoir. I feel a little better already.",
    4997: "My apologies, but this doesn't suit my palate.",
    4998: "I appreciate the gesture, but I can't eat right now.",
    4999: (
        "I'm ^2, a ^0-type, ^1-species Digimon! I didn't exactly want to come to this Farm Island, "
        "you know. But since you begged so nicely, I suppose I'll stay. You'd better be grateful!"
    ),
    5000: "Hey, Taiki. Answer me this: what is the name of Divermon's spear?",
    5001: "Triton",
    5002: "Divermon Spear",
    5003: (
        "Hmm... Correct. I suppose a General should know at least that much. "
        "As your reward, I will personally praise you. Lucky you!"
    ),
    5004: (
        "Just as I thought: simple-minded and wrong. You assumed Divermon's spear was called "
        "'Divermon Spear,' didn't you? I expected it, and I'm still disappointed."
    ),
    5005: "Hey, Taiki. Answer me this: what is Ikkakumon's horn made of?",
    5006: "Mithril",
    5007: "Chrome Digizoid",
    5008: "Correct. That one was far too easy!",
    5009: (
        "Wrong. Your answer, your reasoning, your entire approach—half-baked. "
        "Wash your face and try again. Though there may not be a next time."
    ),
    5010: "Hey, Taiki. Which Digimon uses the toxic-ink attack Black Ink?",
    5011: "Octomon",
    5012: "Gesomon",
    5013: (
        "Yes, correct. Anyone should know at least that much, especially someone who calls himself a General."
    ),
    5014: (
        "No, that's wrong. Squid ink and octopus ink may look alike, but they aren't the same. "
        "Just like 'cute' and 'adorable'—similar, yet completely different!"
    ),
    5015: (
        "Hey, Taiki. Airdramon's Spinning Needle attack creates what by beating its wings?"
    ),
    5016: "Razor wind",
    5017: "A dust cloud",
    5018: "Correct. There's no clever punch line, but praise from me should be reward enough, right?",
    5019: (
        "No. Wrong. More importantly, you answered my question without giving it any thought. "
        "Honestly, you're the worst."
    ),
    5020: "Hey, Taiki. What matters to you when choosing a partner?",
    5021: "Appearance",
    5022: "Feelings",
    5023: (
        "Oh? That's a bold claim. If you can truly judge someone just by looking at them, "
        "I might actually have to respect you."
    ),
    5024: (
        "What a surprisingly dull answer. Do you think another person's feelings are that easy to read? "
        "If you do, you're hopelessly naive."
    ),
    5025: (
        "^P, you have played this game for ^0 hours and ^1 minutes. That's nowhere near enough! "
        "You're going to spend much more time with us, understood?"
    ),
    5026: (
        "Do you understand elemental weaknesses? Plant Digimon, for example, are weak to Fire. "
        "Ignore matchups like that and you'll lose!"
    ),
    5027: (
        "Do you understand elemental resistances? Mythical Beast Digimon, for example, resist Fire. "
        "Put more thought into how you fight!"
    ),
    5028: "I have the Rock Smash field skill! Even the most annoying boulder is no match for me!",
    5029: "I have the Melt Ice field skill! I'll melt any ice blocking our path in one shot!",
    5030: "I have the Tree Cut field skill! I'll slice through any tree blocking our path!",
    5031: (
        "I have the Dig field skill! I can travel underground to reach other places. "
        "You'd better appreciate it!"
    ),
    5032: (
        "I have the Dive field skill! I can travel underwater to reach other places. "
        "You should be grateful!"
    ),
    5033: "I don't have a field skill. Unless you count my breathtaking beauty as a skill!",
    5034: (
        "The new Farm Goods apparently affect our HP and MP. I suppose I could test what they do for you."
    ),
    5035: "The new Farm Goods apparently affect the EXP we earn. I suppose I could test them for you.",
    5036: "The new Farm Goods apparently affect our Attack. I suppose I could test them for you.",
    5037: "The new Farm Goods apparently affect our Spirit. I suppose I could test them for you.",
    5038: "The new Farm Goods apparently affect our Speed. I suppose I could test them for you.",
    5039: "The new Farm Goods apparently affect our Defense. I suppose I could test them for you.",
    5040: "The new Farm Goods apparently help create equipment. I suppose I could test them for you.",
    5041: (
        "We need Farm Goods to grow stronger. Do I really have to explain everything, Taiki? "
        "Go install some already!"
    ),
    5042: (
        "Taiki, do you know the secret to beauty? You must truly believe you're beautiful! "
        "You think that's backward? A chick dives from a branch because it believes it's a bird. "
        "Leap into the sky with enough spirit and you'll remember how to fly! What if it realizes "
        "it has no wings after jumping? How should I know? Maybe it can meow."
    ),
    5043: (
        "What do I like? As if I'd tell you. Even if I did, you probably wouldn't understand. "
        "You're awfully dense."
    ),
    5044: (
        "What do I hate? Childish people, I suppose. I mean maturity, not age. "
        "Some four-year-olds act like adults, while some forty-year-olds act like children. Understand?"
    ),
    5045: (
        "I'm so bored... Asking if anything fun is happening would be a cheap, stupid comment, "
        "and I don't make cheap comments! So, Taiki, entertain me with everything you've got! "
        "Contradictory? Quiet! I'm allowed. Now give me an exciting idea!"
    ),
    5046: (
        "Taiki, can't you make Shoutmon quiet? He never listens, and being near him is exhausting. "
        "You have a great way to stop the noise? DigiFusion with him?! Not a chance! Try it and I'll "
        "shriek in your ear all night!"
    ),
    5047: (
        "This is the worst. The Pickmons tried to recruit me. I thought we'd fuse into some gorgeous "
        "weapon, but they only wanted to make the handle thicker! I knocked them around until they were square."
    ),
    5048: (
        "Taiki, why the long face? Never forget to smile. Smiling only because you're happy is an ugly "
        "way to think. Smile first, then happiness follows, and a happy smile becomes beauty! "
        "You create the result. You seize it!"
    ),
    5049: (
        "Taiki, listen! TEAM CUTE invited me to join! They're the legendary girls' team from the "
        "DigiColiseum. They've been quiet lately, but apparently they're returning with a new lineup. "
        "Me? I turned them down. I'm your partner! Still, I'd love to watch them fight again."
    ),
    5050: (
        "Well, Taiki? Notice anything different? What?! You can't tell? Not at all? Seriously? "
        "Fine, then. I'm not telling you... Idiot."
    ),
    5051: (
        "Taiki, I didn't become your partner just to smolder on this farm forever. "
        "If I can't join a battle hot enough to set my heart ablaze, you may as well delete me now."
    ),
    5052: "Oh? Is it really okay for me to stop working?",
    5053: "Hmm... Fine. I was getting a little tired anyway.",
    5054: "Then quit distracting me and let me work!",
    5055: "Yes, yes... I'll get to work right away, okay?",
    5056: "Oh, this DigiNoir is delicious! I'm feeling much more energetic!",
    5057: "Not bad at all. I feel a little better now.",
    5058: "Ugh, that's awful! What even is this flavor? You can't serve something ridiculous just for a laugh!",
    5059: "Sorry, but I'm not hungry right now.",
    5060: (
        "My name is ^2. I am a ^0-type, ^1-species Digimon. Thank you for inviting me to Farm Island. "
        "I will do my very best to be of service!"
    ),
    5061: "May I ask you something? Zenjiro Tsurugi was the number-one swordsman of which ward?",
    5062: "Koto Ward",
    5063: "Taito Ward",
    5064: (
        "Correct. As expected of you, Taiki. I wonder, if Koto Ward were in the Digital World, "
        "would it be something like the El Est Zone?"
    ),
    5065: (
        "I'm afraid that's incorrect. The answer is Koto Ward. Though, to be honest, "
        "I don't even know which Zone contains Koto or Taito Ward."
    ),
    5066: "May I ask you something? What kind of attack is Veemon's signature move?",
    5067: "A headbutt",
    5068: "An eye poke",
    5069: (
        "Correct. Veemon's signature move, Vee Headbutt, is exactly what it sounds like. "
        "They say it leaves stars sparkling before your eyes. Please don't test it, Taiki, "
        "or you may become a star yourself."
    ),
    5070: (
        "I'm afraid that's incorrect. A sharp V-sign eye poke would suit Veemon, but children might "
        "copy such a move. As for what that implies about Numemon's attack... we shall politely move on."
    ),
    5071: "May I ask you a difficult one? What are the guns carried by Sparrowmon called?",
    5072: "Sanaoria",
    5073: "Sparrow Edge",
    5074: (
        "Correct. They were made by the same gunsmith who created Beelzemon's Berenjena. "
        "Did you learn something new?"
    ),
    5075: (
        "I'm afraid that's incorrect. Don't fall for a name merely because it sounds convincing. "
        "Incidentally, I invented 'Sparrow Edge' just now."
    ),
    5076: "May I ask you something? What is the name of Minervamon's enormous sword?",
    5077: "Olympia",
    5078: "Strike Roll",
    5079: (
        "Correct, Taiki. When Minervamon loses her temper, she sweeps everything away with Olympia. "
        "She may get just a little carried away."
    ),
    5080: (
        "I'm afraid that's incorrect, though you were close. Her sword is Olympia; "
        "Strike Roll is the special move she performs with it."
    ),
}

assert set(_BATCH_3W) == set(range(4929, 5081))
for _global_record, _localized_text in _BATCH_3W.items():
    if _global_record <= 4999:
        _override_key = (2, 24, 129 + (_global_record - 4929))
    else:
        _override_key = (2, 25, _global_record - 5000)
    OVERRIDES[_override_key] = _localized_text

# Batch 3X: global story records 5081-5264.
_BATCH_3X = {
    5081: "Forgive me for asking, but what type of Digimon would be your ideal partner?",
    5082: "The quiet type",
    5083: "The energetic type",
    5084: (
        "Q-Quiet?! I-I see. That's... wonderful. No, um, I didn't mean... "
        "Never mind! Please forget I said anything."
    ),
    5085: "...I see. So that's your preference...",
    5086: (
        "You have played this game for ^0 hours and ^1 minutes. "
        "I hope we will remain together for a very long time!"
    ),
    5087: (
        "Are you familiar with elemental weaknesses? Beast Digimon, for example, are weak to Water. "
        "Please consider each matchup when you fight."
    ),
    5088: (
        "Are you familiar with elemental resistances? Bird Digimon, for example, resist Light. "
        "Please consider each matchup when you fight."
    ),
    5089: "I can use the Rock Smash field skill. I will neatly break any boulder blocking our path.",
    5090: "I can use the Melt Ice field skill. I will neatly melt any ice blocking our path.",
    5091: "I can use the Tree Cut field skill. I will neatly cut down any tree blocking our path.",
    5092: "I can use the Dig field skill. I can escort you underground to another location.",
    5093: "I can use the Dive field skill. I can escort you underwater to another location.",
    5094: (
        "I have no field skill, but I am certain I can help in many other ways! "
        "For example... well... in many ways!"
    ),
    5095: (
        "The newly installed Farm Goods seem to affect our HP and MP. "
        "I am very eager to discover their effect."
    ),
    5096: (
        "The newly installed Farm Goods seem to affect the EXP we earn. "
        "I am very eager to discover their effect."
    ),
    5097: (
        "The newly installed Farm Goods seem to affect our Attack. "
        "I am very eager to discover their effect."
    ),
    5098: (
        "The newly installed Farm Goods seem to affect our Spirit. "
        "I am very eager to discover their effect."
    ),
    5099: (
        "The newly installed Farm Goods seem to affect our Speed. "
        "I am very eager to discover their effect."
    ),
    5100: (
        "The newly installed Farm Goods seem to affect our Defense. "
        "I am very eager to discover their effect."
    ),
    5101: (
        "The newly installed Farm Goods seem to help create equipment. "
        "I am very eager to see what we can make."
    ),
    5102: (
        "To grow stronger, we first need you and the experience of battle. That may be enough for "
        "Digimon in your party, but those on the farm also need Farm Goods. Would you consider installing some?"
    ),
    5103: (
        "What? I seem demure? I cannot decide whether to be pleased or offended. "
        "I merely wear that mask when it suits me. If you could peer into my heart, Taiki, "
        "you would laugh until your knees gave out."
    ),
    5104: (
        "What do I like? You, Taiki. From the moment we met, now and forever... "
        "That was entirely a lie! What I like and dislike is secret. I will not tell you."
    ),
    5105: (
        "What do I dislike? You, Taiki. I cannot bear how my heart stirs whenever we meet... "
        "That was entirely a lie! What I like and dislike is secret. I will not tell you."
    ),
    5106: (
        "Taiki, do your feelings show on your face? Between us, I have quite a temper, "
        "but I smile no matter how angry I become. The more my blood boils, the more sweetly I smile. "
        "That is why no one knows. Whether that is good or bad... I cannot say. Hee hee."
    ),
    5107: (
        "'Visit the website for more!' Forgive me. I simply wanted to say it. "
        "Other phrases linger too: 'Continued on DVD,' 'See it in theaters,' and "
        "'We'll be right back after the break!' They all obsess over what comes next. "
        "Perhaps people secretly fear the future."
    ),
    5108: (
        "Taiki, what are your thoughts on NFAs? Yes, nondeterministic finite automata. "
        "Why are you tilting your head? In that case, I now understand exactly what an "
        "'unreasonable request' feels like."
    ),
    5109: (
        "Which hurts more, Taiki: being the only guest at a party without a gift, or being the only "
        "one not invited? I see. Then what about giving someone a present that is immediately thrown "
        "away, or forcing an obviously unwanted gift on them...? I-I'm not crying! I'm not!"
    ),
    5110: (
        "They say quiet people are frightening when angry, but the truth is the reverse. "
        "Those with terrifying power try hardest to remain gentle. A friend told me that! "
        "A friend, not me. I am far too delicate."
    ),
    5111: (
        "I once thought nothing would frighten me after I became strong. But growing stronger only "
        "means facing stronger opponents. No matter how long I train, the fear always feels fresh!"
    ),
    5112: (
        "I do not seek battle, but neither do I doubt or hesitate when it comes. "
        "In other words, please add me to your party. Whatever our personalities, Digimon need battle."
    ),
    5113: "May I stop working now?",
    5114: "Understood. I will stop working.",
    5115: "Understood. I will keep working a little longer.",
    5116: "Understood. Shall I begin working?",
    5117: "Thank you for the DigiNoir. It was absolutely delicious!",
    5118: "Thank you for the DigiNoir. I feel a little better now.",
    5119: "Cough! Forgive me... Cough! For some reason, this makes me choke...",
    5120: "I am sorry, but I cannot eat anything right now.",
    5121: (
        "I AM ^2, A ^0-TYPE, ^1-SPECIES DIGIMON. I WILL USE THIS FARM FOR A COMPLETE RESET, "
        "THEN UPGRADE MYSELF TO ALL-NEW SPECIFICATIONS!"
    ),
    5122: (
        "NUMEMON HAS AN ALARMING NUMBER OF QUESTIONABLE FANS. DO YOU REMEMBER ITS SIGNATURE MOVE?"
    ),
    5123: "Poop",
    5124: "Punch",
    5125: "CORRECT. AND COMPLETELY DISGUSTING. NO WIT, NO PUNCH LINE, AND NO DIGNITY.",
    5126: (
        "IF ONLY IT WERE PUNCH. SADLY, NUMEMON CANNOT EVEN THROW ONE. "
        "ITS SIGNATURE MOVE IS THE FILTHY, FOUL-SMELLING POOP."
    ),
    5127: (
        "MINOMON CAN SOMETIMES BECOME SHOCKINGLY STRONG. DO YOU REMEMBER ITS SIGNATURE MOVE?"
    ),
    5128: "Pinecone",
    5129: "Mino-Cone",
    5130: "CORRECT. THERE IS NO PARTICULAR TWIST OR PUNCH LINE.",
    5131: (
        "IT SOUNDS CONVINCING BECAUSE IT RESEMBLES THE DIGIMON'S NAME, BUT IT IS WRONG. "
        "ARE YOU MORE GULLIBLE THAN I THOUGHT, TAIKI?"
    ),
    5132: (
        "PARROTMON HAS AN ODDLY LARGE FOLLOWING AMONG MIDDLE-AGED MEN. "
        "DO YOU REMEMBER ITS SIGNATURE MOVE?"
    ),
    5133: "Mjolnir Thunder",
    5134: "Nyolmir Thunder",
    5135: (
        "CORRECT. REPEAT AFTER ME: MJOLNIR, NYOLMIR, MJOLNIR THUNDER! "
        "SAY IT WITHOUT STUMBLING AND I WILL GIVE YOU A MEDAL."
    ),
    5136: "CLOSE! NO, NOT REALLY. IN ANY CASE, THAT ANSWER IS WRONG.",
    5137: (
        "ROSEMON HAS A THORNY LOOK AND PERSONALITY. DO YOU REMEMBER HER SIGNATURE MOVE?"
    ),
    5138: "Roses Rapier",
    5139: "Tiferet",
    5140: (
        "CORRECT. BEING STABBED REPEATEDLY BY THAT THORNY WEAPON SOMEHOW HURTS YOUR FEELINGS TOO."
    ),
    5141: (
        "NO. TIFERET IS THE JEWEL ON ROSEMON'S CHEST. IT MAY BE A WEAPON IN SOME SENSE, "
        "BUT IT IS NOT HER SIGNATURE MOVE."
    ),
    5142: "I HAVE HEARD THAT OUR WAY OF SPEAKING IS VERY DIFFICULT TO UNDERSTAND. IS THAT TRUE?",
    5143: "No",
    5144: "Yes",
    5145: (
        "I KNEW YOU WOULD ACCEPT ME, NO MATTER HOW I SPOKE. THANK YOU."
    ),
    5146: (
        "I SEE. SO I AM DIFFICULT TO UNDERSTAND. PERHAPS I SHOULD STOP USING KATAKANA "
        "AND SPEAK IN THE ALPHABET INSTEAD?"
    ),
    5147: (
        "YOU HAVE PLAYED THIS GAME FOR ^0 HOURS AND ^1 MINUTES. THE BEST IS STILL AHEAD!"
    ),
    5148: (
        "EVERY DIGIMON HAS AN ELEMENTAL WEAKNESS. MYTHICAL BEAST DIGIMON, FOR EXAMPLE, "
        "ARE WEAK TO DARK. IGNORE MATCHUPS AND YOU WILL LOSE BADLY."
    ),
    5149: (
        "EVERY DIGIMON HAS AN ELEMENTAL RESISTANCE. BEAST DIGIMON, FOR EXAMPLE, "
        "RESIST FIGHT. CONSIDER THE MATCHUP BEFORE BATTLE."
    ),
    5150: "MY FIELD SKILL IS ROCK SMASH. I WILL DESTROY A BLOCKING BOULDER IN ONE STRIKE!",
    5151: "MY FIELD SKILL IS MELT ICE. I WILL CLEANLY MELT ANY ICE BLOCKING THE PATH!",
    5152: "MY FIELD SKILL IS TREE CUT. I WILL FELL A BLOCKING TREE IN ONE STRIKE!",
    5153: "MY FIELD SKILL IS DIG. I CAN TAKE AN UNDERGROUND PASSAGE TO ANOTHER LOCATION!",
    5154: "MY FIELD SKILL IS DIVE. I CAN TAKE AN UNDERWATER PASSAGE TO ANOTHER LOCATION!",
    5155: "I HAVE NO FIELD SKILL. IN EXCHANGE, I WILL FIGHT TWICE AS HARD!",
    5156: (
        "THE NEW FARM GOODS APPEAR TO AFFECT OUR HP AND MP. I LOOK FORWARD TO THE RESULTS."
    ),
    5157: (
        "THE NEW FARM GOODS APPEAR TO AFFECT THE EXP WE EARN. I CANNOT WAIT TO SEE HOW MUCH IT INCREASES."
    ),
    5158: (
        "THE NEW FARM GOODS APPEAR TO AFFECT OUR ATTACK. I CANNOT WAIT TO SEE HOW STRONG WE BECOME."
    ),
    5159: (
        "THE NEW FARM GOODS APPEAR TO AFFECT OUR SPIRIT. I AM ALREADY INTELLIGENT, "
        "BUT I WILL TEST THEM."
    ),
    5160: (
        "THE NEW FARM GOODS APPEAR TO AFFECT OUR SPEED. WITH MORE SPEED, WE WILL BE INVINCIBLE."
    ),
    5161: (
        "THE NEW FARM GOODS APPEAR TO AFFECT OUR DEFENSE. AN IRONCLAD GUARD WILL MAKE US STRONGER."
    ),
    5162: (
        "THE NEW FARM GOODS APPEAR TO HELP CREATE EQUIPMENT. I LOOK FORWARD TO SEEING WHAT WE CAN MAKE."
    ),
    5163: "INSTALL SOME FARM GOODS. THEY WILL MAKE US MUCH, MUCH STRONGER!",
    5164: (
        "TAIKI, BETWEEN US, WHY DO LARGE, STRONG, SERIOUS POWER FIGHTERS HAVE SUCH A LUMBERING IMAGE? "
        "IT HAS NOTHING TO DO WITH ME, OF COURSE. MY BODY AND MIND ARE BOTH SLEEK."
    ),
    5165: (
        "WHAT DO I LIKE? ORDERLY THINGS PUT ME AT EASE. "
        "DEALING WITH CARELESS PEOPLE TENDS TO DRAIN MY ENERGY."
    ),
    5166: (
        "WHAT DO I DISLIKE? SLOPPY, CARELESS THINGS. IF THE CORNERS OF A FOLDED ITEM DO NOT ALIGN, "
        "I ALWAYS FEEL A SMALL FLASH OF ANGER."
    ),
    5167: (
        "WHEN YOU MUST DO SOMETHING YOU DO NOT WANT TO DO, START WITH THE TINIEST PIECE. "
        "DO NOT THINK ABOUT THE DISTANT FINISH LINE. TAKE ONE STEP, THEN ANOTHER IF YOU CAN. "
        "EVEN IF YOU STOP HALFWAY, THAT IS FAR BETTER THAN DOING NOTHING."
    ),
    5168: (
        "NOTHING FEELS WORSE THAN FORCING YOURSELF TO ACT CHEERFUL AND FRIENDLY, THEN FAILING TERRIBLY. "
        "YOU REPLAY EVERY AWKWARD MOMENT AND GROAN ALONE. IT IS EXQUISITE... "
        "THIS IS BAD. I MAY ACTUALLY CRY."
    ),
    5169: (
        "LIVING EARNESTLY CAN BE EXHAUSTING, BUT THE THOUGHT OF LIVING CARELESSLY DISGUSTS ME. "
        "IF BOTH ARE DIFFICULT, I WOULD RATHER BE SINCERE. AT LEAST THAT FEELS BETTER."
    ),
    5170: (
        "EVEN WHEN I TRY TO CUT LOOSE, I CANNOT QUITE MANAGE IT. I SECRETLY DO NOT MIND THAT ABOUT "
        "MYSELF... BUT I HATE MYSELF FOR SAYING SOMETHING LIKE THAT."
    ),
    5171: (
        "MY SPEECH TENDS TO BE STIFF, SO I WORKED HARD TO KEEP MY THINKING FLEXIBLE. "
        "THE RESULT? 'THAT GUY IS SURPRISINGLY IRRESPONSIBLE.' WHAT IS THAT SUPPOSED TO MEAN?!"
    ),
    5172: "I HAVE ONE THING I MUST SAY... WHY HAVE I BEEN SPEAKING IN KATAKANA THIS ENTIRE TIME?",
    5173: (
        "I AM TIRED OF LANGUISHING ON THE DIGIFARM. PLEASE ADD ME TO THE PARTY AND TAKE ME INTO BATTLE. "
        "IF I GET ANY MORE BORED, I MAY EXPLODE."
    ),
    5174: "HMM? MAY I STOP WORKING?",
    5175: "ACKNOWLEDGED. STOPPING WORK!",
    5176: "ACKNOWLEDGED. RESUMING WORK!",
    5177: "UNDERSTOOD. WORK ORDER ACCEPTED!",
    5178: "DIGINOIR IS DELICIOUS! SUPER POWER-UP!",
    5179: "DIGINOIR RESTORES A CONSIDERABLE AMOUNT OF ENERGY!",
    5180: "THIS DIGINOIR DOES NOT SEEM TO RESTORE MUCH ENERGY...",
    5181: "I AM TOO FULL TO CONSUME EVEN DIGINOIR...",
    5182: (
        "I'm ^2, a ^0-type, ^1-species Digimon! Oh, yeah! I refuse to fade away on this Farm Island! "
        "I'll train, grow stronger, and become a shining star! Ha-ha!"
    ),
    5183: (
        "Ha-ha! Question time, brother! Gesomon is known as 'the White ___ of the Deep.' Fill in the blank!"
    ),
    5184: "Devil",
    5185: "Squid",
    5186: (
        "Yeah! Correct! That thing really is a devil. It attacks in a rage, then spits toxic ink and "
        "runs when you fight back. Totally irritating and absolutely exhausting, yeah!"
    ),
    5187: (
        "'The White Squid of the Deep'? That's just a description! If you're going to joke, "
        "put some effort into it. Seriously, is that the best choice a General can make?"
    ),
    5188: "Yes! Come on, brother! What are Pukumon's spikes made of?",
    5189: "Chrome Digizoid",
    5190: "Chitin",
    5191: (
        "Yes! Chrome Digizoid is correct! Punch that helmet and you'll hurt yourself worse than Pukumon. "
        "Trading headbutts with that thing is practically suicide, yeah!"
    ),
    5192: (
        "Close! Actually, that was a lie. You weren't close at all! The spikes don't grow from Pukumon. "
        "They're part of its Chrome Digizoid helmet!"
    ),
    5193: "Yo! Super-easy question, brother! What important thing sits at the center of every Digimon?",
    5194: "DigiCore",
    5195: "Another Digimon",
    5196: "Yes, yes, yes! Correct, brother! A digital core: the DigiCore! Mine is seriously hardcore!",
    5197: (
        "What?! A Digimon inside a Digimon, with another Digimon inside that one? "
        "Peel away Digimon after Digimon forever? No way, brother!"
    ),
    5198: "Answer me this, brother! Why does Mushroomon hide half of its face?",
    5199: "It is shy",
    5200: "It is a villain",
    5201: (
        "Oh, yeah! That's correct! Though with a face like that, the shy act is hard to buy. "
        "Show us your face, Mushroomon! Rip that whole mushroom cap off!"
    ),
    5202: (
        "Bzzzzt! Wrong, brother! Hiding your face doesn't automatically make you evil. "
        "Mushroomon may not look it, but it's actually shy!"
    ),
    5203: "General, give me some advice! What matters when you choose a partner Digimon?",
    5204: "Its color",
    5205: "All kinds of things",
    5206: (
        "Color?! For real?! Red, blue, maybe sparkling silver? All right, leave the flash to us. "
        "We'll light the place up, yeah!"
    ),
    5207: (
        "Well, obviously, but tell me which things, brother! It's a secret? Aw, man. "
        "If it's a General's secret, I guess I have to let it go, yeah!"
    ),
    5208: (
        "You've played this game for ^0 hours and ^1 minutes, brother! "
        "Let's keep charging ahead together!"
    ),
    5209: (
        "Every Digimon has an elemental weakness! Mythical Beast Digimon, for example, are weak to Dark. "
        "Ignore matchups and you won't win!"
    ),
    5210: (
        "Every Digimon has an elemental resistance! Beast Digimon, for example, resist Fight. "
        "Use the right matchup and victory is easy!"
    ),
    5211: "My field skill is Rock Smash! I'll crush every boulder blocking our path, yeah!",
    5212: "My field skill is Melt Ice! I'll melt every chunk of ice blocking our path, yeah!",
    5213: "My field skill is Tree Cut! I'll chop down every tree blocking our path, yeah!",
    5214: "My field skill is Dig! I can take an underground tunnel to another location, yeah!",
    5215: "My field skill is Dive! I can take an underwater passage to another location, yeah!",
    5216: "I don't have a field skill! A burning heart and a hardened fist are all I need, yeah!",
    5217: (
        "Those new Farm Goods seem to affect our HP and MP! I can't wait to see what they do!"
    ),
    5218: (
        "Those new Farm Goods seem to affect the EXP we earn! I can't wait to see what they do!"
    ),
    5219: "Those new Farm Goods seem to affect our Attack! I can't wait to see what they do!",
    5220: "Those new Farm Goods seem to affect our Spirit! I can't wait to see what they do!",
    5221: "Those new Farm Goods seem to affect our Speed! I can't wait to see what they do!",
    5222: "Those new Farm Goods seem to affect our Defense! I can't wait to see what they do!",
    5223: (
        "Those new Farm Goods seem to help create equipment! I can't wait to see what we can make!"
    ),
    5224: (
        "Hey, Taiki! This is a pretty good farm, but don't you have Farm Goods that really get the "
        "heart pumping? We need Farm Goods, yeah!"
    ),
    5225: (
        "Hey, Taiki! What's up?! I talked like that and people assumed I was a huge music fan. "
        "Then they got disappointed when their own assumption was wrong. Don't force your image onto "
        "somebody else, yeah!"
    ),
    5226: (
        "Want to know what I like? Battles, DigiNoir, and my brothers! "
        "If I can only choose one, it's my brothers, no question!"
    ),
    5227: (
        "Want to know what I hate? Seeing somebody's shoulders slumped in defeat! "
        "Straighten your back! Head up! Chin down! Mouth closed! Now grit those teeth! "
        "Ha-ha! That's my brother, yeah!"
    ),
    5228: (
        "Taiki, hear me out. I know I'm stronger than I used to be, but I can't tell how much stronger. "
        "I thought the answer would come if I kept trying, but it never does. "
        "So let's keep trying forever—and then a little longer!"
    ),
    5229: (
        "What does losing a battle feel like? Everything goes whoosh, your vision flickers, "
        "then the world goes dark. After the game loads, you sigh with relief and think, "
        "'Man, I thought I was dead!' Yeah!"
    ),
    5230: (
        "Taiki, what do you do when you're mad enough to explode? Deep breaths? Punch a wall? "
        "Think about something else? Those aren't bad, but I recommend going wild and blasting away "
        "the source of your stress! That solves nothing? Who cares? Digimon don't think that far ahead!"
    ),
    5231: (
        "DigiNoir is delicious, but the powder gets everywhere. Here's the clean way to eat it, brother: "
        "stick the whole box in your mouth and pour! Amazing, right? The box won't fit? Don't be picky!"
    ),
    5232: (
        "Ever jerk awake just as you're falling asleep? Happens all the time! Sometimes I fire a special "
        "move in my sleep, then wake up to find everything scorched and wrecked. Nobody speaks to me "
        "for days afterward. Wait... is that only me?"
    ),
    5233: (
        "What's up, Taiki? You look happy! I don't know why, but smiling is always good. "
        "Any face looks better with a grin! Whoa, brother, that's too much. "
        "You're not smiling, you're smirking—and your eyes are scary!"
    ),
    5234: (
        "Yo, Taiki! Take me somewhere! This farm isn't bad, but Digimon need battle, yeah!"
    ),
    5235: "Yeah! Is it okay for me to stop working?",
    5236: "Yeah! I'm stopping the work!",
    5237: "Yeah! I'm back to work!",
    5238: "Yeah! You want me to work?",
    5239: "Woo-hoo! This is seriously delicious! That's DigiNoir for you. I'm overflowing with power!",
    5240: "DigiNoir received! A little power restored!",
    5241: "I got the DigiNoir, but it isn't giving me much power...",
    5242: "I can't eat another bite. My digital stomach is about to overflow...",
    5243: "Training was a huge success!\n\n^5 increased!\n^6 -> ^7",
    5244: "Training was a success!\n\n^5 increased!\n^6 -> ^7",
    5245: "\nTraining failed...",
    5246: "Training was a huge success!\n\nEXP increased greatly!",
    5247: "Training was a success!\n\nEXP increased slightly!",
    5248: "Yes, stop working",
    5249: "No, keep working",
    5250: "Yes, start working",
    5251: "No, never mind",
    5252: "Obtained a consumable item!\n^0",
    5253: "Obtained consumable items!\n^0 x^1",
    5254: "Obtained equipment!\n^0",
    5255: "Obtained equipment!\n^0 x^1",
    5256: "Obtained Farm Goods!\n^0",
    5257: "Obtained Farm Goods!\n^0 x^1",
    5258: "Obtained a key item!\n^0",
    5259: "Obtained ^1 bits!",
    5260: "Obtained ^1 Tamer Points!",
    5261: "Quest complete!",
    5262: "Obtained a DigiScore!\n^0",
    5263: "Obtained DigiScores!\n^0 x^1",
    5264: "Obtained a melody!\n^0",
}

assert set(_BATCH_3X) == set(range(5081, 5265))
for _global_record, _localized_text in _BATCH_3X.items():
    if _global_record <= 5199:
        _override_key = (2, 25, 81 + (_global_record - 5081))
    else:
        _override_key = (2, 26, _global_record - 5200)
    OVERRIDES[_override_key] = _localized_text

# Batch 3Y: global story and encyclopedia records 5265-5394.
_BATCH_3Y = {
    5265: "Obtained melodies!\n^0 x^1",
    5266: "A DigiReport has arrived!\nWould you like to read it?",
    5267: "Yes, read it",
    5268: "No, not now",
    5269: (
        "You found little Terilop and brought him home safely! "
        "I can't possibly thank you enough!"
    ),
    5270: "That's right! I was almost lost, and you rescued me!",
    5271: "You even cheered me up when I was completely exhausted!",
    5272: "This is our way of saying thank you!",
    5273: "We really want you to have it!",
    5274: "It's incredibly rare, and freshly made too!",
    5275: "Please treasure it as if it were one of us!",
    5276: "See you again! Please keep looking after Terilop...",
    5277: "Thank yooou! Teri-lori-lop!",
    5278: (
        "Let me thank you again. I nearly accused poor Numesska of being the kidnapper! "
        "If you hadn't covered for me, things could have gotten ugly. "
        "Whatever happens, you must keep this absolutely secret. Understood?!"
    ),
    5279: (
        "I will not forgive anyone who defiles this sacred sea! "
        "You shall atone for your sins forever on the ocean floor!"
    ),
    5280: (
        "W-Wait a second! You can't be serious! The ocean here is incredibly deep, isn't it? "
        "If I sink that far, the pressure will squash me flat!"
    ),
    5281: "Silence!",
    5282: (
        "Th-This is bad. He's seriously furious... Mermaimon is facing the greatest crisis of her life!"
    ),
    5283: (
        "Aaaaaah?! H-Hey, wait! You arrived at the perfect time, brave champion of justice! "
        "Please, please, help me! Help meee!"
    ),
    5284: (
        "Who are you? An ally of this criminal? If you are merely passing through, then keep walking. "
        "I am about to sink this offender to the ocean floor. Interfere, and you will join her!"
    ),
    5285: (
        "I'm not her ally. If anything, she's my enemy. But one of her friends begged me to save her. "
        "They said I was the only one who could do it. That's why I came, and I won't walk away. "
        "If you intend to sink her, I can't stand by and let it happen!"
    ),
    5286: (
        "None who have incurred my wrath have returned alive. "
        "Lie forever on the dark ocean floor and regret your choice!"
    ),
    5287: (
        "I see. You truly are not her ally, yet I understand your desire to protect them. "
        "In recognition of your courage, I will pardon her crime. Strong one, use your power for good."
    ),
    5288: "Amazing! You actually defeated him... You really saved me. Thank you so much!",
    5289: (
        "Let me reward you with some treasure! I hid four treasures around Tokona Sea and Tokona Coast. "
        "Find them and you may take one. They'll disappear after I leave, so hurry and choose!"
    ),
    5290: "That's generous, but what kind of treasure is it?",
    5291: (
        "It's a secret! Treasure is exciting precisely because you don't know what it is, right? "
        "The treasures sparkle, so they'll be easy to spot. Hurry and find my token of gratitude!"
    ),
    5292: (
        "Is this the suspicious stone monument Patamon mentioned? "
        "Well, it certainly looks suspicious..."
    ),
    5293: (
        "You who touch my seal... You who summon calamity... "
        "You who disturb an ancient slumber and awaken its wrath... Show me your resolve!"
    ),
    5294: "Do not break the seal... Do not awaken us from our sleep...",
    5295: "Wh-What was that just now...?",
    5296: (
        "You who touch my seal... You who summon calamity... "
        "You who disturb an ancient slumber and awaken its wrath... Show me your resolve!"
    ),
    5297: "Do not break the seal... Do not awaken us from our sleep...",
    5298: "It repeated the exact same words... What does that mean?",
    5299: (
        "You who touch my seal... You who summon calamity... "
        "You who disturb an ancient slumber and awaken its wrath... Show me your resolve!"
    ),
    5300: "Do not break the seal... Do not awaken us from our sleep...",
    5301: "It only says the same thing over and over. What's going on here?",
    5302: "Are you the master of those stone monuments?",
    5303: (
        "Stone monuments? You mean those cursed seals?! I placed a curse on the accursed things myself! "
        "Now every Ancient Digimon will become my servant. I will revive them all and rule the Digital World! "
        "My ambition is only one step from completion!"
    ),
    5304: (
        "Darn it! So you're the one who angered the beings inside the monuments! "
        "Not a chance! I won't let you do this!"
    ),
    5305: "You're already too late!",
    5306: "Now awaken, Ancient Digimon!",
    5307: "Please... Stop him... Stop the Ancient Digimon...",
    5308: (
        "Thank you. You saved us. AncientWisemon controlled our minds and made us forget ourselves."
    ),
    5309: (
        "We will return to our slumber. This time, we pray that nothing will ever wake us again."
    ),
    5310: "Everything should be all right now. Good night, everyone.",
    5311: (
        "As a token of our gratitude, we entrust you with this legendary score. "
        "Farewell, worthy bearer of great power."
    ),
    5312: (
        "I'm glad they gave it to me, but what kind of score is this? "
        "Maybe I should go back and ask Patamon."
    ),
    5313: "What's wrong, Parrotmon? I heard you were looking for me...",
    5314: "...Parrotmon?",
    5315: "What the...? Something is definitely wrong with it!",
    5316: "WE WILL MULTIPLY. MORE AND MORE OF US WILL APPEAR.",
    5317: "NO ONE CAN STOP US.",
    5318: "Multiply? And who's 'us'? What are those things?",
    5319: "You're acting suspicious. What are you doing here?",
    5320: "GRRRR... KRRRK! KRRRK! GRRRRRR...",
    5321: (
        "What is wrong with this thing? Forget suspicious - it looks completely broken."
    ),
    5322: "Oh, come on... Not this routine again!",
    5323: "GRRRRRRRRRRRRRRR...!",
    5324: "WE WILL KEEP MULTIPLYING. MORE AND MORE... KRRRK!",
    5325: "NO ONE CAN STOP US. GRRRR...",
    5326: "That again? Who is 'us'? What exactly are you creatures?!",
    5327: "They still haven't given up?!",
    5328: (
        "WE WILL MULTIPLY FOREVER. COPY OURSELVES, THEN COPY THE COPIES, THEN COPY THEM AGAIN. "
        "WE WILL... KEEP... MULTIPLYING... KRRRK!"
    ),
    5329: "Hmm... For now, let's go back and report this to Veemon.",
    5330: "They multiplied this much already?!",
    5331: "K-KRRRK! OBSTRUCTION APPROACHING. HOSTILE INTERFERENCE DETECTED...",
    5332: "GRRRRR... ELIMINATE THE OBSTRUCTION.",
    5333: "KRRRRRK... NO ONE CAN STOP US.",
    5334: "Huh? Where did all of them go?",
    5335: (
        "You've got to be kidding! Don't tell me this one little thing was the true form "
        "of that entire swarm of Digimon!"
    ),
    5336: (
        "G-GRRR... I'M SO SORRY! I'LL NEVER DO IT AGAIN! "
        "I'LL LEAVE THIS PRECIOUS TREASURE DATA, SO PLEASE FORGIVE ME!"
    ),
    5337: (
        "At that size, it shouldn't be able to cause any more trouble. "
        "Let's return to Sky Fort and report to Veemon!"
    ),
    5338: (
        "Dummy data\n123456789012345678901234567\n123456789012345678901234567\n"
        "123456789012345678901234567\n123456789012345678901234567\n"
        "123456789012345678901234567"
    ),
    5339: (
        "A small Digimon whose baby fuzz has fallen away as its body has grown. "
        "Despite its size, it is a lively member of the Dragon family and is always bursting with energy."
    ),
    5340: (
        "A mysterious Digimon that suddenly appeared on computer networks. "
        "It is said to have hatched from a DigiEgg filled with humanity's destructive impulses. "
        "It multiplies like a pathogen and corrupts entire networks."
    ),
    5341: (
        "A being called Digi-Entelecheia: the power that governs evolution given Digimon form. "
        "It is said to possess the ability to help other Digimon evolve."
    ),
    5342: (
        "A small purple Dragon Digimon overflowing with energy. It loves a good fight, "
        "never backs down from any opponent, and greets every challenger with its powerful fists."
    ),
    5343: (
        "A Reptile Digimon that grew strong enough to walk on two legs. "
        "With hard claws on its hands and feet and Baby Flame from its mouth, "
        "it bravely confronts any opponent."
    ),
    5344: (
        "A lively, purehearted Dragon Digimon descended from a species that flourished "
        "at the dawn of the Digital World. It retains the potential to Armor Digivolve with DigiEggs."
    ),
    5345: (
        "A Rookie Dragon Digimon with the potential of a combat species. "
        "The Digital Hazard on its belly warns of power that could damage computer data, "
        "but used for peace, that same power can protect the world."
    ),
    5346: (
        "Its old-style forehead interface suggests it may be a Prototype Digimon from before "
        "Digimon were discovered. It has fierce combat instincts, bonds with anything it bites, "
        "and holds the potential to become tremendously powerful."
    ),
    5347: (
        "A four-legged Amphibian Digimon. It is normally gentle and quiet, but when angered, "
        "it shocks everything nearby without distinction."
    ),
    5348: (
        "It gathered data left by Garurumon and wears the resulting pelt for protection. "
        "Usually shy, it becomes bold and confident whenever it has the pelt on."
    ),
    5349: (
        "A Mammal Digimon known for enormous wing-like ears. It can fly, but only at about "
        "one kilometer per hour, so walking is faster. It can Armor Digivolve with DigiEggs."
    ),
    5350: (
        "A Chick Digimon whose wings developed like arms. It lives on the ground and flies away "
        "when danger approaches, though no faster than Patamon. It dreams of soaring freely one day."
    ),
    5351: (
        "A Digimon with a tropical flower blooming from its head. The flower's scent changes with "
        "its mood: sweet when happy, but so overpowering when angry that even large Digimon flee."
    ),
    5352: (
        "The foundational form of Insect Digimon. It loves nature and lives at a relaxed pace. "
        "Unlike many aggressive insect species, it is kindhearted and protected by a hard shell and claws."
    ),
    5353: (
        "A Mineral Digimon with powerful defenses created by covering itself in mineral data. "
        "The composition of that data changes according to where and under what conditions it develops."
    ),
    5354: (
        "An aquatic Digimon that swims by using its large tail as a propeller. "
        "Its body has not fully solidified after so long underwater. It sometimes climbs onto rocks "
        "to practice its voice."
    ),
    5355: (
        "A seal-like Digimon capable of living on land. Warm fur covers its body; "
        "as it grows, the fur becomes longer and apparently changes from white to brown."
    ),
    5356: (
        "A small bat-like Digimon rumored to have tempted the once-angelic Devimon onto the path of evil. "
        "It avoids the front lines, instead using its cunning to cause trouble everywhere."
    ),
    5357: (
        "Said to have been created by a child online who imitated Agumon. "
        "Though timid, it cannot ignore wrongdoing and loves interacting with children over the network. "
        "When startled, the blocks forming its body scatter."
    ),
    5358: (
        "A gear-shaped Digimon packed with gears inside. If even one is lost, its entire body stops. "
        "It can transmit computer viruses that allow it to control the infected target."
    ),
    5359: (
        "An experimental new-generation Digimon created by Digimon researchers. "
        "Because it has not yet discovered its purpose, its upbringing can lead it toward either good or evil."
    ),
    5360: (
        "A timid, gentle Larva Digimon. It is too weak to challenge large Digimon directly, "
        "but Armor Digivolution through a DigiEgg can grant it astonishing power."
    ),
    5361: (
        "A courteous, calm Bird Digimon descended from an ancient species. "
        "It can borrow the power of DigiEggs to Armor Digivolve."
    ),
    5362: (
        "A Mammal Digimon whose body is covered by a hard shell. "
        "As a descendant of an ancient species, it can Armor Digivolve through DigiEggs."
    ),
    5363: (
        "One of a pair of twin Digimon, distinguished by the single horn on its head. "
        "Its bright, cheerful nature hardly suggests a combat species, but it unleashes tremendous power in battle."
    ),
    5364: (
        "One of a pair of twin Digimon, distinguished by three horns and a tendency to cry. "
        "Unlike energetic Terriermon, it is shy and lonely, but reveals deep reserves of power when necessary."
    ),
    5365: (
        "A Digimon whose growth strongly reflects its relationship with its Tamer. "
        "Careful training from an early stage can produce an exceptionally intelligent individual. "
        "It excels at speed-based combat rather than raw power."
    ),
    5366: (
        "A mischievous Digimon resembling a little demon. Proud and fiercely competitive, "
        "it never flatters or submits to the powerful. In truth, however, it is terribly lonely."
    ),
    5367: (
        "The Digivolved form of Tsumemon. Its huge mouth can destroy over one hundred megabytes "
        "of data each second, so a computer it infiltrates is quickly devastated. "
        "It regards destroying data as nothing more than play."
    ),
    5368: (
        "A ninja-like Bird Digimon. It moves with remarkable speed by using its wings skillfully "
        "and specializes in bewildering its opponents."
    ),
    5369: (
        "A Bird Digimon discovered in a computer at an Antarctic base. "
        "Its wings have regressed and it walks slowly, but those small wings make it a skillful swimmer."
    ),
    5370: (
        "A cunning Goblin Digimon that loves mischief but never defies a stronger opponent. "
        "It carefully maintains its mohawk every day. Its signature move is Goblin Strike."
    ),
    5371: (
        "A bivalve Digimon enclosed in a hard shell. It lures opponents with its cute face before "
        "attacking them. Its shell shrugs off minor blows, while the body inside has a slime-like form."
    ),
    5372: (
        "A cold-weather subspecies of Agumon that adores snowy regions. "
        "When it fights in the snow, its body coloring provides natural camouflage."
    ),
    5373: (
        "A crab-like Digimon that coats itself in metal data dissolved in the Net Ocean. "
        "It boasts enormous pincers and a hard shell, but its joints and underbelly remain vulnerable."
    ),
    5374: (
        "A Digimon whose entire face resembles a flower. It normally wears its petal-like shell "
        "as a helmet to protect its head, but opens the petals wide whenever it is in a good mood."
    ),
    5375: (
        "A Plant Digimon resembling a flower bud. It rotates the leaves on its head to float through "
        "the air. Though expressionless, its face is charming, and its gentle nature keeps it mindful of its friends."
    ),
    5376: (
        "A Beast Digimon with sharp claws. It protects its hands with gloves until the claws mature. "
        "Its specialty is a swift hit-and-run style that strikes before darting away."
    ),
    5377: (
        "A Digimon that wears a holy ring as an earring on its left ear. "
        "The ring gradually stores sacred power, and the amount accumulated is said to influence its next Digivolution."
    ),
    5378: (
        "A turtle-like Digimon carrying a shell shaped like a computer mouse. "
        "It can hide its entire body inside the shell, except for the helmet on its head."
    ),
    5379: (
        "A vampire Digimon that loves pranks. It becomes so focused on making a prank succeed "
        "that it forgets to drink blood and fearlessly accepts even dangerous challenges."
    ),
    5380: (
        "A Puppet Digimon born from data leaked by a computer chess game. "
        "Though currently weak, this common foot soldier holds the potential to rise to Mega-class power."
    ),
    5381: (
        "A Digimon resembling a poisonous mushroom, with many small mushrooms growing across its body. "
        "Their attacks cause various symptoms. It loves bullying the weak, but is secretly extremely shy."
    ),
    5382: (
        "A stag beetle-like Digimon with a head and arms resembling stun guns. "
        "When threatened, it releases one million volts of electricity. "
        "It recharges by consuming electricity and is normally docile."
    ),
    5383: (
        "The Rookie form Digivolved from Sunmon. Energetic and intensely curious, it carries "
        "the fiery power of the sun within its body and excels at striking enemies with blazing fists."
    ),
    5384: (
        "The Rookie form Digivolved from Moonmon. A little shy around strangers, it carries the power "
        "of pure water within its body. In battle, it attacks with cute claws infused with Dark power."
    ),
    5385: (
        "A Chick Digimon that has only just begun sword training. It is brimming with confidence, "
        "yet has not noticed that pieces of its eggshell are still stuck to its body."
    ),
    5386: (
        "An Angel Digimon with the appearance of a child. It arose during an age of chaos and is said "
        "to have brought peace to the Digital World. Despite its youthful form, its power and wisdom "
        "can surpass even Ultimate Digimon."
    ),
    5387: (
        "A Digimon designed for smaller Digimon to ride. It has no will of its own and cannot move "
        "without a rider, but directly reflects that rider's power. Its unpredictable fighting style "
        "makes it dangerous to underestimate."
    ),
    5388: (
        "A yellow dinosaur-like Digimon whose hardened head skin forms a defensive shell. "
        "Its sharp claws and enormous horn provide tremendous attack power. "
        "Highly intelligent, it also excels at teamwork."
    ),
    5389: (
        "A Digimon resembling an ancient dinosaur. Despite its frightening appearance, it is calm, "
        "intelligent, and relatively easy to tame. In battle its instincts awaken, and it sweeps foes "
        "away with tackles, powerful arms, and its massive tail."
    ),
    5390: (
        "A Fallen Angel Digimon known for its black clothing and tattered wings. "
        "Once an angel, it was corrupted by evil and now bears a large wicked emblem on its chest. "
        "Though vicious, it faithfully serves any master with whom it forms a pact."
    ),
    5391: (
        "A rare Digimon that crosses the Digital World's skies on enormous wings. "
        "So few exist that it is considered mythical and close to a divine being. "
        "It possesses the power to summon storms and tornadoes."
    ),
    5392: (
        "A long, snake-like Digimon that lives near water. It is surprisingly gentle and usually "
        "swims at a leisurely pace, but reveals a savage side whenever battle begins."
    ),
    5393: (
        "A slug-like Digimon that prefers dark, damp environments. It has neither the strength nor "
        "the will to fight and lives freely each day. When attacked, it throws poop to make the enemy recoil."
    ),
    5394: (
        "A bright blue beetle-like Digimon whose large body overflows with power. "
        "A hard shell provides excellent defense, and its metal-plated head is especially durable."
    ),
}

assert set(_BATCH_3Y) == set(range(5265, 5395))
for _global_record, _localized_text in _BATCH_3Y.items():
    if _global_record <= 5337:
        _override_key = (2, 26, 65 + (_global_record - 5265))
    else:
        _override_key = (3, 0, _global_record - 5338)
    OVERRIDES[_override_key] = _localized_text

# Batch 3Z: global encyclopedia records 5395-5469.
_BATCH_3Z = {
    5395: (
        "A wolf-like Digimon whose fur is as durable as the legendary rare metal mithril. "
        "The blades on its shoulders can slice anything they touch. Highly intelligent, "
        "it remains faithfully devoted to its master."
    ),
    5396: (
        "An Angel Digimon clad in six wings and pure-white robes. A being of absolute good, "
        "it is said to guide every Digimon toward happiness. Against evil, however, "
        "it is severe and attacks without mercy."
    ),
    5397: (
        "A carnivorous Plant Digimon known for long vine-like arms and a huge open mouth. "
        "It lures small Digimon with a sweet scent, then captures them with its vines. "
        "As it grows, it apparently blooms and bears fruit."
    ),
    5398: (
        "A short-tempered, battle-loving Digimon resembling an ogre. Called the Digimon Hunter "
        "for challenging opponents stronger than itself, it carries a bone club claimed as a trophy "
        "from SkullGreymon."
    ),
    5399: (
        "A Ghost Digimon formed from a cursed virus program. It destroys any computer it possesses "
        "in an instant. What lies beneath its white cloth remains unknown, and its shadow is said "
        "to connect to a black hole."
    ),
    5400: (
        "A golden, poop-shaped Digimon said to have arisen when waste data gathered and suddenly mutated. "
        "The Chuumon clinging to it serves as its brain, using wicked ideas to coax Sukamon into mischief."
    ),
    5401: (
        "A chicken-like Digimon that lost the ability to fly after living on the ground for so long. "
        "Its two legs became extremely powerful instead. Though aggressive, it dislikes battles "
        "that consume too much energy."
    ),
    5402: (
        "A righteous Digimon known as both the King of Beasts and the Noble Hero. "
        "Daily training has forged its dependable body, and it battles evil with the sword "
        "Shishioumaru at its hip."
    ),
    5403: (
        "A stag beetle Digimon protected by a hard shell and armed with enormous head pincers. "
        "It possesses tremendous power but little beyond pure combat instinct, making it highly dangerous. "
        "It is Kabuterimon's sworn enemy."
    ),
    5404: (
        "A frog-like Digimon that attracts listeners with a beautiful voice unlike anything its appearance "
        "would suggest. Three holes in its tongue produce harmonies, amplified through the horn around its neck."
    ),
    5405: (
        "A small cat-like Digimon whose tail bears a Holy Ring, proof of its sacred nature. "
        "Without the ring it cannot use its full power. It wears claws copied from SaberLeomon's data "
        "and can Armor Digivolve with DigiEggs."
    ),
    5406: (
        "A Wizard Digimon from a Digital World in another dimension. It came to train toward becoming "
        "a great mage. Extremely shy, it refuses to show its true face to anyone."
    ),
    5407: (
        "A giant cactus Digimon that stores nutrient data in its body, allowing it to survive for long "
        "periods in barren places. It moves at its own relaxed pace, but also has a surprisingly hardworking side."
    ),
    5408: (
        "A Machine Digimon with exceptional defense. Infection by a malignant virus erased its emotions, "
        "leaving only its defense program. Virus Digimon exploit that power and use it for their own purposes."
    ),
    5409: (
        "A Mythical Dragon Digimon that conceals tremendous power. Attacks from its muscular arms and legs "
        "can pulverize huge rocks. Its strong sense of justice keeps it from using that power recklessly."
    ),
    5410: (
        "A humanoid Insect Digimon with high defense from its hard shell. Coolheaded and gifted as an assassin, "
        "it uses swift movement and precise judgment to target an enemy's vital points."
    ),
    5411: (
        "A gigantic Bird Digimon wreathed in blazing fire. Said to have been born from the Internet's "
        "defensive Firewall, it crosses the network by beating its enormous flaming wings."
    ),
    5412: (
        "An Armored Dragon Digimon covered in hard scales. Solid protrusions on its head make its tackles "
        "especially destructive. Though gentle by nature, it possesses a courageous heart."
    ),
    5413: (
        "A Hunter Digimon skilled at tracking prey. It captures targets precisely with speed that belies "
        "its appearance, and can leap high enough to fly. Its favorite jeans are custom-made."
    ),
    5414: (
        "A Demon Dragon Digimon with a crimson body and white mane. It has the ferocity typical of a Virus type, "
        "but with the right upbringing it can grow into a Digimon that fights for justice."
    ),
    5415: (
        "A fox Digimon with nine tails tipped by blue flames. It is said to Digivolve from highly experienced "
        "Renamon. Its powerful will supports mastery of many mystical techniques."
    ),
    5416: (
        "Keramon's chrysalis form, storing energy to become stronger. It cannot move, but its hard skin "
        "shrugs off enemy attacks. It retaliates using the tentacles on its back."
    ),
    5417: (
        "A Digimon resembling the legendary sacred beast Shisa. Its power repels calamity and becomes "
        "overwhelming against evil. It risks danger to protect the kindhearted, but normally relaxes in sunlight."
    ),
    5418: (
        "A Little Devil Digimon said to be an archetype of Dark Digimon. Mischievous and slightly contrary, "
        "it often teams up with its good friend DemiDevimon to play pranks."
    ),
    5419: (
        "A hawk-like Bird Digimon with a large horn. It flies at Mach speed and never overlooks even tiny prey, "
        "diving sharply to attack with its horn and beak."
    ),
    5420: (
        "A pirate-captain Mutant Digimon sailing the Net Ocean in pursuit of the legendary White Whamon. "
        "This fearless sea warrior has a hook for one arm and a cannon for the other."
    ),
    5421: (
        "A heavyweight Beast Dragon Digimon whose shadow alone sends many Digimon fleeing. "
        "In battle it reveals a beast's savagery, but its draconic intelligence makes it extremely calm at other times."
    ),
    5422: (
        "A Cyborg Digimon rebuilt from a wild Digimon base. Its athletic ability was so extreme that "
        "heavy Chrome Digizoid plating was added to restrain its performance."
    ),
    5423: (
        "A legendary Digimon with golden fur, said to possess the power to defeat malicious computer viruses. "
        "It races through networks atop a cloud-like object, making encounters exceptionally rare."
    ),
    5424: (
        "A cosmic Mutant warrior equipped with star-shaped armor, gloves, and boots. "
        "Its eyes burn with fighting spirit, and it can silently convey its will to others. "
        "It greatly admires the hero Leomon."
    ),
    5425: (
        "An Invader Digimon related to Nanimon, with a body made entirely of explosives and hair like a fuse. "
        "This ultimate bomb fanatic's danger level is at the absolute maximum."
    ),
    5426: (
        "A Mythical Beast Digimon combining a unicorn's horn with a pegasus's wings. "
        "It races across networks and impales enemies with its sharp horn. "
        "Wild individuals are violently untamed and dangerous to approach."
    ),
    5427: (
        "A black Dinosaur Digimon believed to be a Tyrannomon corrupted by a malicious computer virus. "
        "Driven into a frenzy, it attacks everything that enters its sight."
    ),
    5428: (
        "A unicorn-like Digimon covered in pure-white fur. Mithril-hard skin beneath the fur withstands "
        "any cold. It releases heat through its soles, melting ice as it walks."
    ),
    5429: (
        "A bull-like Digimon wielding powerful Dark energy. Its tough hide ignores ordinary attacks, "
        "and the formidable weapon Demon Arm is fused to its left arm."
    ),
    5430: (
        "A special Dragon Digimon believed to be a Greymon subspecies. "
        "Its head armor and entire body have developed like living weapons, giving it a more aggressive form."
    ),
    5431: (
        "A larger form of Gaomon whose once-protected claws have fully grown. "
        "Though quadrupedal, its legs are strong enough to let it stand like a bear and strike enemy Digimon."
    ),
    5432: (
        "An ancient Bird Digimon called a living fossil. Its wings are poorly suited for flight, "
        "but powerful legs let it run at 200 kilometers per hour. It attacks anything that moves, "
        "and metal in its feathers provides high defense."
    ),
    5433: (
        "A weasel-like Digimon with a sentient blade for a tail. The blade warns it of attacks from behind, "
        "though the two occasionally quarrel even in the middle of battle."
    ),
    5434: (
        "A sunflower-like Plant Digimon energized by sunlight, which also raises its attack power. "
        "On clear days, it sometimes flies by flapping the leaves on its back."
    ),
    5435: (
        "A fusion of data from a music player and the legendary kappa. Always cheerful and in rhythm, "
        "it constantly listens to its favorite music. A scratch on the disc atop its head makes it cry."
    ),
    5436: (
        "A noble vampire-wolf Digimon said to have existed since the Digital World's creation. "
        "It drains every byte from a victim's DigiCore and can travel by decomposing its own body into data."
    ),
    5437: (
        "A Bird Digimon that can fly but runs even faster on its powerful legs. "
        "Steel feathers are hidden beneath its wings, and it specializes in high-speed combat."
    ),
    5438: (
        "A mole-like Digimon living deep underground. Its huge nose drill tunnels at high speed. "
        "Normally gentle but fond of pranks, it sometimes steals favorite bones that Garurumon buried."
    ),
    5439: (
        "A ferocious Beast Man Digimon covered in dark-brown fur. It releases shock waves that shatter rock "
        "and manipulates time and space to warp through dimensions or create special spaces."
    ),
    5440: (
        "A Mutant Digimon whose body is made of earth and closely resembles Frigimon. "
        "Despite its heavy appearance, it can move with surprising speed."
    ),
    5441: (
        "An Aquatic Digimon that resembles a shrimp but belongs to the Dramon family. "
        "A hard shell and huge pincers protect its fierce body. It lives deep in the Net Ocean "
        "and should be approached with caution."
    ),
    5442: (
        "An octopus-like Digimon wearing objects collected from the Net Ocean. Its claws came from "
        "Devidramon data, while Fujitsumon living on the pot atop its head warn it of danger."
    ),
    5443: (
        "A squid-like Digimon whose fearsome appearance hides great intelligence. It avoids pointless battles, "
        "but violently attacks trespassers. Its mouth sprays toxic ink that paralyzes the entire body."
    ),
    5444: (
        "A Digimon whose structure resembles an ancient fish. Limb-like fins and a head covered in tough skin "
        "provide excellent offense and defense. It is considered a precious ancestor of many Digimon species."
    ),
    5445: (
        "A hermit crab-like Aquatic Digimon with a hard shell and very soft body. "
        "It inhabits anything large enough to hold it and changes homes as it grows. "
        "Some Shellmon become as large as small mountains."
    ),
    5446: (
        "An Ice-Snow Digimon formed from snow and ice crystals. Its body is freezing cold but its heart "
        "is warm, so it avoids battle whenever possible and lives each day at a relaxed pace."
    ),
    5447: (
        "A Fallen Angel Digimon with a cold heart and body. Without mercy or emotion, it uses many "
        "ice techniques designed to make its opponents suffer."
    ),
    5448: (
        "A dolphin-like Aquatic Mammal Digimon apparently born from communication-research software. "
        "Highly intelligent and peace-loving, it nevertheless retaliates without restraint when challenged."
    ),
    5449: (
        "A vicious Plant Digimon resembling a withered tree. It disguises itself as an ordinary tree "
        "to ambush passersby. Its thick trunk offers superb defense, but it cannot approach Fire Digimon."
    ),
    5450: (
        "A mantis-like Insect Digimon said to have been created in a laboratory to eliminate Virus Digimon. "
        "Cold and relentless, it finishes chosen targets with the sharp sickles on both arms."
    ),
    5451: (
        "A bee-like Insect Digimon that flies at extreme speed. Its wingbeats overwhelm hearing, "
        "while the regenerating stinger on its tail carries exceptionally dangerous venom."
    ),
    5452: (
        "A dragonfly-like Insect Digimon that races through networks and attacks with sharp fangs. "
        "It can discharge Lightning from its tail."
    ),
    5453: (
        "A ninja Digimon recognized by its red mask. It practices Iga-style ninjutsu, hides in forests "
        "and water, and quietly travels from place to place while continuing its training."
    ),
    5454: (
        "A Machine Digimon marked by its large clock. It manages network space-time and freely controls time. "
        "Though neutral by choice, it counterattacks aggressors without mercy."
    ),
    5455: (
        "A Mutant Digimon believed to be related to Mamemon. Its magnetic body constantly emits electricity. "
        "Though small, it meets attacks with electric shocks, punches, and kicks."
    ),
    5456: (
        "A tank-like Digimon that loves conflict and joins any faction that benefits it. "
        "It possesses terrifying power and riddles approaching enemies with weapons mounted across its body."
    ),
    5457: (
        "A Mineral Digimon made of ninety percent rock. Barely alive through the bonds connecting its limbs, "
        "this earthen doll cannot move without orders. An ancient forbidden inscription is carved into its back."
    ),
    5458: (
        "A gunman-like Mutant Digimon whose body resembles a gun barrel. Its blood burns for justice "
        "at the sight of evil, but it loves gambling and may spare villains who beat it at Russian roulette."
    ),
    5459: (
        "A Digimon with a human upper body and beastlike lower body. Its trained right arm is fused with a weapon, "
        "and blue material within its body forms protective armor. Back-mounted vents enable extreme speed."
    ),
    5460: (
        "An evil Dragon Digimon summoned to the Dark Area by Devimon. It flies through darkness on eerie wings, "
        "paralyzes victims with its crimson stare, then tears them apart with blade-like claws."
    ),
    5461: (
        "A spider-like Insect Digimon consumed by a computer virus. Its cursed touch corrodes anything. "
        "Once it selects prey, its eight legs pursue the target until escape becomes impossible."
    ),
    5462: (
        "A rare Mythical Dragon Digimon often mistaken for a dog. It possesses exceptional attack power "
        "and can exceed Ultimate-class strength in a crisis. The V-shaped mark on its chest is its trademark."
    ),
    5463: (
        "A Demon Man Digimon born when an overseas game was infected by a virus. "
        "Its ruined armor records endless battles, and its sword Shiratorimaru bears a spell that drains life."
    ),
    5464: (
        "A white, horse-shaped Puppet Digimon carrying giant darts. Poor at close combat, "
        "it disrupts enemies with a thoroughbred's powerful legs and leaps high enough to clear them."
    ),
    5465: (
        "Coronamon's Champion form. Now quadrupedal, it combines a beast's power and agility. "
        "Its Flame Dive launches it skyward on back-mounted wings before it charges the enemy wreathed in fire."
    ),
    5466: (
        "Lunamon's Champion form. It bounds around with tremendous jumping power. "
        "Its Moon Night Bomb throws sleep-infused bubbles created by the Moon Gloves on both hands."
    ),
    5467: (
        "A Command Dragon aspiring to become a Virus Buster. Metal plates place it in Commander Mode. "
        "Though kindhearted, it fights Virus Digimon until nothing remains but dust."
    ),
    5468: (
        "Hyokomon's Champion form. It became a wandering swordsman and earns a living as a bodyguard. "
        "It accepts any paid job, yet still shows kindness toward the weak."
    ),
    5469: (
        "A Fire Digimon bearing the power of the Ten Legendary Warriors. Its DigiCore is wrapped in "
        "the sacred flame known as Spiritual Fire, granting complete control of fire. "
        "It is both incarnation and guardian of the Firewall."
    ),
}

assert set(_BATCH_3Z) == set(range(5395, 5470))
for _global_record, _localized_text in _BATCH_3Z.items():
    if _global_record <= 5437:
        _override_key = (3, 0, 57 + (_global_record - 5395))
    else:
        _override_key = (3, 1, _global_record - 5438)
    OVERRIDES[_override_key] = _localized_text

# Batch 4A: global encyclopedia records 5470-5546.
_BATCH_4A = {
    5470: (
        "A massive, powerful Cyborg Digimon and friendly rival of Etemon. "
        "When its anger peaks or its excitement exceeds maximum voltage, the volcano on its back erupts. "
        "It specializes in deep-bass microphone performances."
    ),
    5471: (
        "A Cyborg Digimon Digivolved from Greymon, with more than half its body mechanized. "
        "Its attack power is said to equal a nuclear warhead, and its chest hatch launches organic missiles."
    ),
    5472: (
        "A lovable Puppet Digimon resembling a giant stuffed bear. The zipper on its back has inspired rumors "
        "that someone is inside. Victims of Lovely Attack become so happy that they lose all desire to fight."
    ),
    5473: (
        "An Undead Digimon born when a body obsessed with battle continued moving after its flesh decayed, "
        "leaving only bones. With no emotions and nothing but combat instinct, it is feared by all other Digimon."
    ),
    5474: (
        "A Cyborg Digimon that greatly enhances Mamemon while remaining just as small. "
        "Ninety percent of its body is mechanical, and its left arm carries the devastating Psycho Blaster."
    ),
    5475: (
        "An experimental humanoid Cyborg Digimon created in pursuit of the perfect cyborg. "
        "Every action is programmed, and it can defeat nearly any Digimon below Ultimate level with one strike."
    ),
    5476: (
        "A mysterious Puppet Digimon that calls itself the King of Digimon. "
        "Its reinforced monkey suit withstands any attack as it travels the world seeking battles. "
        "Rumor claims it secretly controls Monzaemon."
    ),
    5477: (
        "A Cyborg Digimon modified by humans and programmed to destroy everything. "
        "Its power lets it breach even heavily protected computer networks, and both arms launch organic missiles."
    ),
    5478: (
        "A small Fairy Digimon that casts magic by reciting programming languages from another dimension. "
        "It seals an enemy's abilities before delivering a powerful blow. Its spear Fairy Tale can make computers run wild."
    ),
    5479: (
        "An Ultimate Digimon shaped like the DigiEgg that represents every Digimon's beginning and end. "
        "Its egg-like exoskeleton is exceptionally hard, and its attack is said to leave victims unable to rise again."
    ),
    5480: (
        "An Ancient Beast Digimon resembling a mammoth. It has tremendous power but fares poorly in heat. "
        "The ancient wisdom carved into its mask grants farsight and hearing capable of detecting distant sounds."
    ),
    5481: (
        "Kuwagamon's Digivolved form, with greatly improved defense. Its aggressive nature compels it to destroy "
        "everything it sees. Enhanced antennae locate targets, while stronger pincers slice them apart."
    ),
    5482: (
        "An Amphibian Digimon Digivolved from Gekomon, with topknot-like antennae. "
        "Rumored to have emerged from a karaoke scoring system, it plays melodies through shoulder horns "
        "and sings in a dignified bass register."
    ),
    5483: (
        "A Great Angel Digimon resembling a beautiful woman. Normally gentle, it never tolerates injustice "
        "and attacks until wrongdoers repent. Its spirit and power have earned worship as a Digital World goddess."
    ),
    5484: (
        "Gatomon's Armor Digivolution through the DigiEgg of Reliability. It moves underwater like a jet "
        "and can identify a scent from one kilometer away, allowing it to pursue chosen prey anywhere."
    ),
    5485: (
        "An Ancient Crustacean Digimon born when a virus infected a research database on prehistoric life. "
        "Head tentacles seize targets, its tail blade finishes them, and a radar eye locates enemies while it hides."
    ),
    5486: (
        "An Aquatic Digimon evolved from Seadramon to survive harsher environments. "
        "A lightning-shaped blade grows from its head, its shell and body are larger and tougher, "
        "and it pursues prey like a torpedo until the target falls."
    ),
    5487: (
        "An Aquatic Beast Man Digimon evolved from a virus that infected ship computers and disrupted navigation. "
        "Its tentacles bundle into a humanoid form that conceals an ugly true body. It is called the Destroyer of the Deep."
    ),
    5488: (
        "A Beast Man Digimon Digivolved from Garurumon and now capable of walking on two legs. "
        "It has excellent all-around combat ability, a strong sense of justice, and unwavering loyalty to its master's orders."
    ),
    5489: (
        "The king of Undead Digimon, revived through dark magic. It can resurrect data destroyed by computer viruses "
        "as malicious viruses. Extremely cunning and difficult to banish, its power reportedly weakens during daylight."
    ),
    5490: (
        "A high-ranking Fallen Angel Digimon with a woman's form and immense dark-side power. "
        "Very few have ever been successfully raised on personal devices. It uses a terrifying attack that incinerates enemies."
    ),
    5491: (
        "A Bird Man Digimon that values justice and protects nature, the earth, and wind. "
        "When the Digital World's order is disturbed, it appears to guide events back onto the proper path. "
        "It is a close friend of the hero Leomon."
    ),
    5492: (
        "A giant flower-shaped Plant Digimon with many tentacles growing from its body. "
        "Gentle and reclusive, it lives quietly near water. Each change of season sheds its petals and produces new ones."
    ),
    5493: (
        "A Fairy Digimon born from a flower, said to create a refreshing breeze whenever it flies. "
        "Though fickle and mischievous, it is kind to the small and weak and opens its heart to girls of similar temperament."
    ),
    5494: (
        "Kabuterimon's Digivolved form, discovered in a tropical Net Area. It apparently flies better than "
        "the blue MegaKabuterimon. Its expression reveals little, but witnesses have seen it knightly protect the weak."
    ),
    5495: (
        "A microscopic Machine Digimon developed for medical treatment. Originally meant to repair broken computers, "
        "an attack by a powerful Virus Digimon damaged its thought circuits. It now disrupts healthy computers instead."
    ),
    5496: (
        "A Dragon Man Cyborg Digimon clad in armor made from special rubber. "
        "The armor offers excellent defense while amplifying its natural attack power. "
        "It appears without warning to eliminate Virus Digimon from networks."
    ),
    5497: (
        "A Great Angel Digimon charged with supervising many Angel Digimon. Usually serving as a priest, "
        "it enters Battle Mode when darkness appears and fights with the holy sword Excalibur. "
        "Eight shining silver wings adorn its back."
    ),
    5498: (
        "A Dragon Man Digimon formed by the DNA Digivolution of ExVeemon and Stingmon. "
        "Its draconic traits dominate, combining a dragon's power with an insect's shell. "
        "It will risk its life to protect its master."
    ),
    5499: (
        "A Mutant Digimon formed by the DNA Digivolution of Stingmon and ExVeemon. "
        "Its insect traits dominate. Four wings grant swift flight, while compound eyes precisely track enemies."
    ),
    5500: (
        "A rabbit-like Holy Beast Digimon from Eastern legend. It freely manipulates the qi flowing through its body, "
        "allowing graceful movement or a crushingly heavy strike."
    ),
    5501: (
        "A cunning Demon Beast Digimon resembling the Spider Queen of Greek myth and commanding every Dokugumon. "
        "It excels at taking human form; anyone who approaches carelessly becomes prey in an instant."
    ),
    5502: (
        "A mummy-like Undead Digimon wrapped in bandages. Called a Necromancer for summoning and controlling "
        "the spirits of Digimon, it becomes especially dangerous when cornered and wildly fires its gun Obelisk."
    ),
    5503: (
        "A crimson Virus Cyborg Digimon known as Great Growlmon. Its upper body is plated in Chrome Digizoid, "
        "and shoulder verniers enable flight. It can attack both aerial and ground targets."
    ),
    5504: (
        "A Cyborg Digimon Digivolved from Gargomon and known as the Keen Hound. "
        "It hunts with near-light-speed movement, uses large ear-shaped radar to detect distant targets, "
        "and fires homing missiles."
    ),
    5505: (
        "A Demon Man Digimon Digivolved from Kyubimon. A master of yin-yang arts, it lives in darkness "
        "and attacks with talismans, incantations, and many weapons concealed within its long sleeves."
    ),
    5506: (
        "A giant parrot Digimon that wandered through a space-time rift into the Digital World. "
        "It attacks discovered targets with its talons and can call down lightning."
    ),
    5507: (
        "A spider-like Digimon capable of entering any computer network. In Normal Mode it extends its head and limbs; "
        "in Cocoon Mode it retracts them for higher defense, but can then travel only in a straight line."
    ),
    5508: (
        "A rare panda-shaped Puppet Digimon with a blunt, unfriendly personality. "
        "It considers itself a lone wolf but secretly envies popular Monzaemon. In battle, it is surprisingly capable."
    ),
    5509: (
        "A deep-sea Digimon related to Devimon. Solitary life in the abyss erased every emotion except hatred, "
        "so it keeps attacking even after opponents surrender. Each tentacle on its back seems to possess its own will."
    ),
    5510: (
        "A Demon Man Digimon resembling the crow tengu. It trains while wandering mountains and practices Shugendo, "
        "freely invoking mysterious divine powers. Its twin Irataka Swords seal powerful curses."
    ),
    5511: (
        "A fox-like Digimon whose entire body resembles sharp blades and indiscriminately slices nearby objects. "
        "Its speed is so great that victims are cut apart the instant a whirlwind appears."
    ),
    5512: (
        "A chicken-like Holy Bird Digimon with nearly impenetrable steel armor and the pestle Baochu, "
        "which creates lightning strikes. It absorbs nearby electricity and can accidentally cause blackouts."
    ),
    5513: (
        "A colossal Beast Dragon Digimon called the Final Enemy, born when hidden DigiCore data was released. "
        "Its overwhelming body crushes foes, and one sweep of its wings reflects incoming attacks."
    ),
    5514: (
        "An Aquatic Beast Man Digimon that swims the Net Ocean in a wetsuit. Cheerful and friendly, "
        "its body is perfectly adapted to underwater combat. It attacks with its favorite harpoon, Triton."
    ),
    5515: (
        "A Composite Digimon assembled from many Digimon, possessing terrifying combat instincts and destructive power. "
        "Its organic components have led to theories that it was either a Machinedramon prototype or built to oppose one."
    ),
    5516: (
        "A bipedal Horned Dragon Digimon resembling a Triceratops. Its hide and two forehead horns are extremely hard, "
        "with the horns said to surpass Monochromon's. Gentle by nature, it nevertheless possesses immense power."
    ),
    5517: (
        "A Beast Man Digimon formed by the DNA Digivolution of Aquilamon and Gatomon. "
        "It leaps high and glides on its outstretched arms. Ear-mounted radar displays captured targets "
        "on its head-mounted screen."
    ),
    5518: (
        "Starmon's Ultimate Mutant form. Even more self-satisfied, it battles eagerly in flashy clothes and sunglasses. "
        "It can summon countless meteorites."
    ),
    5519: (
        "Ikkakumon's bipedal Digivolution. Armor of hide and shell protects its trained muscles, "
        "and it reshaped its nonregrowing horn into a saw. It wields Thor Hammer, excavated from ancient ice."
    ),
    5520: (
        "A whale-like Aquatic Mammal Digimon living deep in the Net Ocean. "
        "It contains more data than ordinary computers can process and can generate enormous tidal waves."
    ),
    5521: (
        "A bean-sized Mutant Digimon created by sudden mutation in a harsh environment. "
        "Unthinkably small for an Ultimate, it possesses absolute power feared even by other Ultimate Digimon."
    ),
    5522: (
        "Gotsumon's Ultimate Mineral form, covered in ore data. It looks almost identical to Gotsumon, "
        "but its power is immeasurable and it can manipulate vast cosmic energy."
    ),
    5523: (
        "A dark-dragon Cyborg Digimon created by further modifying Megadramon into a dedicated aerial interceptor. "
        "Its signature move Genocide Gear launches countless missiles together with beams from both arms."
    ),
    5524: (
        "A huge Cyborg Digimon with more than half its body mechanized. Despite its size it can take flight, "
        "shooting enemies with a powerful Chrome Digizoid revolver built into its left arm."
    ),
    5525: (
        "A Cyborg Digimon carrying rocket engines with enormous thrust. Its airtime is short, "
        "but momentary maximum acceleration makes it excellent at hit-and-run attacks."
    ),
    5526: (
        "An ancient Holy Beast Digimon said to have arisen at the Digital World's creation. "
        "Though only Ultimate level, legend grants it Mega-level strength. Peaceful and compassionate, "
        "it punishes those who cause conflict severely."
    ),
    5527: (
        "A Fairy Digimon as beautiful as the beloved lilac flower. Pure and innocent, "
        "it also bears the solemn responsibility of governing both rebirth and death."
    ),
    5528: (
        "A vampire dancer Digimon said to have emerged from a museum's folk-dance database. "
        "It perfected its own dance, Bulldog, using fluttering clothes to distract targets before "
        "slashing them with a hidden arm-mounted rapier."
    ),
    5529: (
        "Gatomon's Armor Digivolution through the DigiEgg of Purity. Huge flowers bloom from its head and hands. "
        "It loves glamorous places and strikes dramatic poses even during battle."
    ),
    5530: (
        "Woodmon's Digivolved form, a powerful and intelligent Plant Digimon called the Master of the Forest. "
        "It lures lost travelers deeper with hallucinogenic mist, then absorbs them as nutrients through vines and tentacles."
    ),
    5531: (
        "A Mutant Digimon born when a desktop trash bin came alive. The can containing its body resembles a black hole; "
        "anything sucked inside vanishes from the Digital World. Its can-made bazooka fires poop."
    ),
    5532: (
        "The ultimate Demon Lord Digimon, combining holy and demonic power. "
        "It is the fallen form of the once-angelic Lucemon and schemes to destroy the world once, "
        "then create a new one in its place."
    ),
    5533: (
        "A tiny helmeted Dragon Mutant Digimon. Despite its size it is extremely aggressive, "
        "attacking territorial intruders without discussion and earning the name Tiny Tyrant."
    ),
    5534: (
        "A Mine Digimon that patrols computer networks and repels unauthorized intruders. "
        "Once it identifies an enemy, it attacks at full power and self-destructs to defeat the target when cornered."
    ),
    5535: (
        "An alien-like Digimon shrouded in mystery and rumored to have been born from plant fruit. "
        "Despite its huge head and octopus-like lower body, it possesses astonishing attack power."
    ),
    5536: (
        "A Cyborg Digimon rebuilt for ground interception. Its reinforced body deflects attacks, "
        "and its powerful jaws crush anything. It fires missiles from the right arm and lasers from the left."
    ),
    5537: (
        "A Puppet Digimon hiding inside a cute Tyrannomon plush toy. Its power and defense rival Monzaemon's, "
        "but without someone to control it, it becomes nothing more than a decoration."
    ),
    5538: (
        "An Armored Dragon Digimon that charges with a sturdy body and crimson horns as hard as diamonds. "
        "It can breathe an enormous fireball from its mouth."
    ),
    5539: (
        "A reaper-like Ghost Digimon carrying a giant chain sickle. The space beneath its cloth connects "
        "to a Digital World in another dimension, and possession by Phantomon is said to be invariably fatal."
    ),
    5540: (
        "A bull-like Holy Beast Digimon with a black, four-legged body clad in red armor. "
        "It resembles a mighty warrior, and the twin swords in its hands are said to cleave mountains."
    ),
    5541: (
        "A legendary Holy Dragon Digimon evolved from a Veedramon that survived countless battles. "
        "New wings enable flight, while its battle-specialized body provides tremendous offense and defense."
    ),
    5542: (
        "Leomon's Ultimate Beast Man form. High-speed rotating armor covers all four limbs. "
        "A warrior who mastered secret techniques, it fights evil with attacks as swift and powerful as a whirlwind."
    ),
    5543: (
        "A Warrior Digimon clad in heavyweight Chrome Digizoid armor and effortlessly wielding a greatsword. "
        "The armor restrains its runaway power. It serves its master faithfully, whether that master is good or evil."
    ),
    5544: (
        "A long-necked Dragon Digimon closely resembling an ancient dinosaur. "
        "Despite its enormous body, it is gentle and spends its days at a leisurely pace."
    ),
    5545: (
        "A kappa-like Demon Man Digimon said to have been banished from the Digital World's heavens. "
        "Usually calm and collected, it transforms into a terrifying creature if even one bead "
        "is lost from the necklace sealing its DigiCore."
    ),
    5546: (
        "A three-legged crow Digimon whose wing-mounted vajras generate sacred energy. "
        "Legend says it guides chosen individuals toward the golden land hidden within the Digital World."
    ),
}

assert set(_BATCH_4A) == set(range(5470, 5547))
for _global_record, _localized_text in _BATCH_4A.items():
    if _global_record <= 5537:
        _override_key = (3, 1, 32 + (_global_record - 5470))
    else:
        _override_key = (3, 2, _global_record - 5538)
    OVERRIDES[_override_key] = _localized_text

# Batch 4B: global encyclopedia records 5547-5628.
_BATCH_4B = {
    5547: (
        "A Puppet Digimon skilled in artillery techniques. Its attacks cover tremendous range and distance, "
        "allowing it to strike enemies from far away."
    ),
    5548: (
        "A fortress-like Digimon famous for impregnable defense. It blocks enemy attacks behind an iron wall, "
        "then counterattacks with speed completely unexpected from such an enormous body."
    ),
    5549: (
        "Firamon's Ultimate form, now standing upright for the close combat it favors. "
        "Its signature move Crimson Beast King Wave launches fighting spirit combining fire and a lion's power from its fists."
    ),
    5550: (
        "Lekismon's Ultimate form, capable of exceptional speed. It wields the moon-marked weapons Nox Luna "
        "in both hands, shredding enemies with graceful, dance-like movement through its signature Lunatic Dance."
    ),
    5551: (
        "Veemon's Armor Digivolution through the DigiEgg of Courage. It draws out one hundred percent of the "
        "DigiEgg's Fire attribute and attacks with the fierce intensity of blazing flames."
    ),
    5552: (
        "One of the thirteen Royal Knights, born when Veemon Armor Digivolves through the DigiEgg of Miracles. "
        "Its Chrome Digizoid armor provides outstanding defense, while miraculous power overcomes any crisis."
    ),
    5553: (
        "Patamon's Armor Digivolution through the DigiEgg of Kindness. It excels at digging underground. "
        "Its timid nature sometimes sends it burrowing rapidly to safety when danger approaches."
    ),
    5554: (
        "Wormmon's Armor Digivolution through the DigiEgg of Miracles. "
        "This heavyweight power fighter has a shining golden metal body and is said to create miracles "
        "with the sacred weapon Vajra."
    ),
    5555: (
        "Hawkmon's Armor Digivolution through the DigiEgg of Purity. It blends into nature like a ninja, "
        "attacking from an enemy's blind spot. Both arms and legs can extend like long springs."
    ),
    5556: (
        "Armadillomon's Armor Digivolution through the DigiEgg of Friendship. "
        "Its right hand is a forklift and its left a power shovel, making it useful for any construction project."
    ),
    5557: (
        "A Digimon generated by an algorithmic bug. Countless vine-like tentacles let it dominate vast fields. "
        "While doing so, it transforms into the parasitic form known as Worm Phase."
    ),
    5558: (
        "A high-defense Digimon formed by the DNA Digivolution of Angemon and Ankylomon. "
        "Its appearance suggests an angel that descended upon the ancient Digital World. "
        "Its neck and torso rotate 360 degrees, enabling attacks in every direction."
    ),
    5559: (
        "An evil Digivolution of the Seadramon family. Its blade-like head horn controls Dark power. "
        "More cunning than before, it pursues prey with even greater persistence than MegaSeadramon."
    ),
    5560: (
        "An Undead Digimon reconstructed from fossil data. Black spiritual energy overflowing from its DigiCore "
        "fills every Digimon with mortal terror. Its signature move is Grave Bone."
    ),
    5561: (
        "A dual-sword Warrior Digimon called the Golden Meteor. Its swordsmanship is said to exceed even "
        "Royal Knight Crusadermon's. Its royal-blue cape is an honor awarded for distinguished battle achievements."
    ),
    5562: (
        "A Dinosaur Digimon evolved from a Tyrannomon that survived fierce battles. "
        "Like a master instructor, it trains younger Tyrannomon to become full-fledged warriors."
    ),
    5563: (
        "A completely mysterious Digimon that can emerge anywhere in time and space through its book. "
        "Researchers believe it may share a family with the Demon Man Digimon Piedmon."
    ),
    5564: (
        "A mermaid-like Digimon whose beautiful singing captivates listeners. "
        "Its powerful greed and obsession with treasure lead it to plunder even other Digimon's data."
    ),
    5565: (
        "Buraimon's Ultimate form, resembling a military commander. It sweeps foes away with a gigantic greatsword "
        "whose single blow can shatter a mountain. As its strength nears perfection, it has begun to feel emptiness "
        "in battles that only destroy."
    ),
    5566: (
        "A Beast Man Digimon called the cat goddess. Flashy and cunning, it uses the jewels covering its body "
        "and its uncanny gaze to manipulate others. Graceful and fast, it is also strong enough for its claws "
        "to slice through rock."
    ),
    5567: (
        "A Demon Beast Digimon called the Watchdog of Hell. Its body is protected by a living shell that steadily "
        "repairs damage. Each shoulder armor has its own awareness and alerts Cerberumon to attacks from any direction."
    ),
    5568: (
        "A Flame Digimon burning even hotter than Meramon. Its signature move Ice Phantom launches ice as cold "
        "as dry ice, paradoxically inflicting severe burns on its target."
    ),
    5569: (
        "An Insect Digimon called the Desert Assassin. Its tail stinger injects venom so subtly that victims die "
        "without realizing they were struck. Targets never even learn of its presence, earning it the assassin title."
    ),
    5570: (
        "Gatomon's Armor Digivolution through the DigiEgg of Light. It draws out the DigiEgg's Light attribute "
        "to its fullest, gaining tremendous power capable of dispelling darkness."
    ),
    5571: (
        "The ultimate Insect Digimon, evolved with data from both Kabuterimon and Kuwagamon. "
        "Its giant horn and pincers compensate for both species' weaknesses, and it flies across the Digital World "
        "at supersonic speed."
    ),
    5572: (
        "An ancient lion-like Beast Digimon rumored to be Leomon's ancestor or beast form. "
        "All details remain mysterious, though it is known to move at Mach speed."
    ),
    5573: (
        "Etemon's Mega form, created by converting itself into a full-metal cyborg. "
        "Using data collected through countless battles, it rebuilt its injured body entirely in Chrome Digizoid."
    ),
    5574: (
        "A cute Fairy Digimon rarely seen in its Net Ocean habitat. The Holy Ring around its neck suggests "
        "a connection to sacred Digimon. It generally avoids battle."
    ),
    5575: (
        "A Cyborg Digimon also known as the Super-Large Assault Landing Craft. "
        "Longer than Whamon, it can transport multiple Digimon inside and possesses attack power worthy of its vast size."
    ),
    5576: (
        "A clown-like Demon Man Digimon whose unpredictable appearances and entire nature remain mysterious. "
        "Its power is so great that anyone encountering it can only curse their own fate."
    ),
    5577: (
        "A Demon Lord Digimon commanding Devil and Fallen Angel Digimon. Once a high-ranking Angel, "
        "it defied the forces of good and was banished to the Dark Area, leaving it consumed by hatred for them."
    ),
    5578: (
        "The Mega Holy Bird form, bearing four shining golden wings. "
        "It leads all Bird Digimon and is also said to preside over sacred-species Digimon."
    ),
    5579: (
        "A Puppet Digimon carved from the body of a cursed Cherrymon. Though resembling a marionette, "
        "it acts by its own will. A compulsive liar, it is often responsible when computers display false information."
    ),
    5580: (
        "A rose-like Fairy Digimon called the Queen of Flowers. The jewel Tiferet on its chest is said to promise "
        "eternal beauty and strength to its bearer. It desires to remain beautiful forever."
    ),
    5581: (
        "The seasoned Mega warrior of the Greymon family, clad in Chrome Digizoid armor. "
        "It carries Dramon Killers on both arms and the Brave Shield on its back, with dramatically enhanced speed and power."
    ),
    5582: (
        "The Mega form of the Garurumon family, strengthened by metalization without losing speed. "
        "Its cyborg body hides many weapons, a nose-mounted Laser Sight locks onto enemies, "
        "and beam wings allow ultra-high-speed flight."
    ),
    5583: (
        "A full-metal Cyborg Digimon assembled from parts of many cyborg species. "
        "It possesses extraordinary strength and intelligence but no will of its own. "
        "An unknown entity implanted an evil program in its DigiCore, endlessly supplying malicious power."
    ),
    5584: (
        "A Demon Beast Digimon with a shell-covered upper body and beastlike lower body. "
        "It is Myotismon's true power released, but the form thinks only of rampaging, "
        "so the elegant and intelligent Myotismon despises it."
    ),
    5585: (
        "An ultimate ancient Dragon Digimon from a forgotten age. Its immense power is difficult to control, "
        "allowing it to become either benevolent or evil. Beyond its dragon form, another form supposedly uses all its power."
    ),
    5586: (
        "A Demon Lord Digimon once ranked among the highest Angels before falling into the Dark Area. "
        "Unlike other Fallen Angels, it remains neutral between good and evil, but is said to become a god of destruction "
        "for the final battle."
    ),
    5587: (
        "A Seraph Angel Digimon clad in holy armor and bearing ten golden wings. "
        "It holds the highest angelic rank and governs Angel Digimon. Together with Ophanimon and Cherubimon Good, "
        "it forms the Three Great Angels."
    ),
    5588: (
        "A Cyborg Digimon completed by improving the unfinished Andromon with additional Chrome Digizoid parts. "
        "It gained independent thought, enabling extremely precise and powerful attacks against Virus Digimon."
    ),
    5589: (
        "A Mutant Digimon said to be Digitamamon's dark Digivolution and a living Pandora's box. "
        "Containing all the Digital World's evil, it hates everything and uses magic from a lost ancient "
        "high-level programming language for destruction."
    ),
    5590: (
        "A beastlike Cherub Angel Digimon capable of tremendous lightning attacks resembling divine punishment. "
        "Together with Seraphimon and Ophanimon, it forms the Three Great Angels."
    ),
    5591: (
        "The corrupted Virus form of Cherubimon Good, one of the Three Great Angels. "
        "It retains tremendous lightning techniques whose force resembles divine punishment."
    ),
    5592: (
        "One of the thirteen Royal Knights, the highest network-security order. Though a Virus type, it protects the Net, "
        "but becomes dangerous when balance collapses. Its holy Chrome Digizoid armor accompanies lance Gram and shield Aegis."
    ),
    5593: (
        "A colossal Machine Digimon whose entire body is a mass of weapons. It moves slowly because its energy is diverted "
        "into unbelievable destructive power, and it can counter attacks arriving from any direction."
    ),
    5594: (
        "A priestess Digimon charged with conveying divine will. It assumes a shrine maiden form for rituals and uses "
        "yin-yang techniques to purge evil or erect barriers. Four Pipe Foxes hidden in its belt assist in battle and scouting."
    ),
    5595: (
        "A Digimon called the Devil that absorbs network data, repeatedly growing and Digivolving as it rampages. "
        "This herald of destruction ultimately intends to seize a military computer and launch nuclear missiles at humanity."
    ),
    5596: (
        "A Sea Man Digimon ruling all Aquatic Digimon. Its light, strong scale mail is made from Blue Digizoid, "
        "granting excellent mobility, while one strike from its giant spear delivers immense power."
    ),
    5597: (
        "A Digimon born when a hacker-created computer virus suddenly mutated. Small but fiercely competitive, "
        "it challenges any opponent. Its head is a Chrome Digizoid Metal Head."
    ),
    5598: (
        "A Mythical Beast Digimon formed by combining parts from Bird, Beast, and other Digimon. "
        "It apparently hides in desert and mountain caves. Its speed and attack power make it an Internet data guardian."
    ),
    5599: (
        "A mysterious long-necked Dragon Digimon discovered by a laboratory studying unidentified creatures. "
        "It appears on misty days but rarely shows itself, and its cry fills listeners with sadness."
    ),
    5600: (
        "A Cyborg Digimon developed around the same time as Andromon. Its human-based body grants emotion and great power, "
        "but an uncontrollable accident caused every official record of its existence to be erased."
    ),
    5601: (
        "An extravagant Mutant Digimon called the Prince of the Mamemon World, born by loading royal data. "
        "Its crown and cape derive from royal records, and a smile never leaves its face."
    ),
    5602: (
        "A Throne Angel Digimon standing at the summit of female Angels and embodying divine compassion. "
        "Together with Seraphimon and Cherubimon Good, it forms the Three Great Angels."
    ),
    5603: (
        "A brave Demon Man Digimon commanding Musyamon forces from the front. Its horse-like lower body maintains balance "
        "while it swings swords in fierce combat. The enormous blade in its right hand is Ryuzanmaru."
    ),
    5604: (
        "An elderly Ancient Digimon said to have existed since the Digital World's creation. "
        "This all-knowing elder reportedly guided chosen humans when the world once fell into crisis."
    ),
    5605: (
        "An elderly-woman Ancient Digimon rumored to be Rosemon transformed by a villain's curse, though nobody knows the truth. "
        "One sweep of the magic broom in its right hand can erase malicious viruses instantly."
    ),
    5606: (
        "A Divine Being Digimon called the Judge of Digimon and guardian of the Dark Area. "
        "It rebirths arriving data as DigiEggs, seals evil data in darkness, and can summon demonic beasts from hell."
    ),
    5607: (
        "A one-eyed spider-like Parasite Digimon that possesses other Digimon and controls them at will. "
        "It draws out a host's full ability, but drives the possessed Digimon into a savage frenzy."
    ),
    5608: (
        "A metal-plated, four-legged Dragon Digimon armed with a long-range cannon. "
        "It combines powerful cannon fire with heavy armor, while its tail delivers dangerous blows to nearby enemies."
    ),
    5609: (
        "An Angel Digimon leading angelic armies at the front. Its entire body resembles sharp blades that violently "
        "slice enemies apart. Even among Angels, it is uniquely specialized for offense."
    ),
    5610: (
        "A giant Bird Digimon wrapped in golden Chrome Digizoid armor that repels every attack. "
        "Its duty is said to be eliminating foreign objects that infiltrate the Digital World."
    ),
    5611: (
        "An imaginary Digimon created by a DigiCore's fantasies. Its tremendous form embodies Destruction "
        "and incarnates the Ultimate Enemy. Its power is too great for an ordinary Tamer to control."
    ),
    5612: (
        "A solitary Demon Lord Digimon that prefers acting alone. Too proud to join a mob against the weak, "
        "it carries two beloved shotguns named Berenjena."
    ),
    5613: (
        "A courageous Beast Man Digimon loyal only to its own justice, confronting anyone who violates that code as evil. "
        "Only Digimon who defeat powerful enemies without losing heart are said to earn the title Bancho."
    ),
    5614: (
        "A dark Cyborg Digimon believed to be the D-Brigade's Final Decisive Weapon. "
        "It wanders in search of a target code-named BAN-TYO, with the Gigastick Lance built into its right hand."
    ),
    5615: (
        "A Cyborg Digimon artificially created by studying captured Vademon data. "
        "It was reportedly built with extraterrestrial technology at a facility known as Area 51."
    ),
    5616: (
        "A dark Demon Beast Digimon emerging from the deepest Dark Area, with a body as large as a mountain. "
        "The mouth in its lower body supposedly connects to the abyss; anything swallowed has its DigiCore pulverized."
    ),
    5617: (
        "A golden Holy Dragon Digimon concealing a Dragon Digimon in each hand. It releases divine energy, "
        "and its God Flame detonates that energy to strike an opponent no matter where it hides."
    ),
    5618: (
        "The Mega form of the Seadramon family, fully covered in Chrome Digizoid and rebuilt for combat. "
        "Its metal body repels attacks, while unrivaled aquatic speed makes it overwhelmingly strong underwater."
    ),
    5619: (
        "A pure-white Warrior Digimon that moves faster than sight. Its demonic sword Fenrir Sword freezes anything it cuts, "
        "while the golden bird Freyja traveling beside it warns of danger."
    ),
    5620: (
        "A righteous Cyborg Digimon that arrives with its red scarf streaming. A hero admired by young Digimon, "
        "it never tolerates wrongdoing and Digivolves from Cyberdramon."
    ),
    5621: (
        "A Beast Man Digimon ruling the frozen lands and commanding armies of Ikkakumon and Zudomon. "
        "Its fur rivals Chrome Digizoid in hardness. Merciless to enemies but caring toward followers, "
        "it carries the weapon Mjolnir on its back."
    ),
    5622: (
        "A black Virus-type WarGreymon whose beliefs oppose the original's, yet it follows its own justice. "
        "This proud warrior despises cowardice and refuses to consider deceitful Virus Digimon its allies."
    ),
    5623: (
        "A Mammon reduced to bones after infection while battling Virus Digimon. Destruction of its exposed DigiCore "
        "would mean its true end. Though emotionless, it still remembers its mission to eliminate Virus types."
    ),
    5624: (
        "The final form of the Kuwagamon family, living deep in forests and active only at night. "
        "Its terrifying hidden power earned the name Devil of the Deep Forest. HercuKabuterimon is its eternal rival."
    ),
    5625: (
        "A ruler of many regions in the ancient Digital World, said to Digivolve from mummy-like Digimon. "
        "Legends that countless Digimon built mysterious ruins under its command demonstrate its immense authority."
    ),
    5626: (
        "One of the thirteen Royal Knights, charged with restraining the others themselves. "
        "Because it never reveals its form, it is also called the Master of the Empty Seat."
    ),
    5627: (
        "A Holy Dragon Digimon considered the ultimate form of sacred beasts. It wields righteous light that erases evil. "
        "Rarely seen and of unknown habitat, it reportedly appears whenever evil energy arises in the Digital World."
    ),
    5628: (
        "A Composite Digimon born from Machinedramon's overwhelming power and Chimeramon's diverse data. "
        "The cause of their fusion remains unknown. It is said to control dimensions and space freely."
    ),
}

assert set(_BATCH_4B) == set(range(5547, 5629))
for _global_record, _localized_text in _BATCH_4B.items():
    OVERRIDES[(3, 2, 9 + (_global_record - 5547))] = _localized_text

# Batch 4C: global encyclopedia records 5629-5712.
_BATCH_4C = {
    5629: (
        "An Evil Dragon Digimon born when WarGrowlmon followed a mistaken Digivolution. It spreads hatred and seeks "
        "to destroy everything it sees, almost as if it were the dangerous power of the Digital Hazard itself."
    ),
    5630: (
        "One of the thirteen Royal Knights. Its six-legged beast form moves at extreme speed beneath highly defensive "
        "Red Digizoid armor. It carries the holy crossbow Muspelheim and holy shield Niflheim."
    ),
    5631: (
        "A Light Dragon Digimon that stores the searing energy of the sun for battle. Its radiant wings overflow "
        "with light, and it can summon GeoGrey Sword, a blade concentrating the power of the earth."
    ),
    5632: (
        "A Beast Knight Digimon fully covered in Chrome Digizoid armor. It moves at such absurd speed that opponents "
        "see mirage-like phenomena. It also commands a broad variety of techniques."
    ),
    5633: (
        "A giant Cyborg Digimon that sacrificed the durability of its metal shell to install beam ports across its body. "
        "The overwhelming barrage from those weapons perfectly embodies the belief that offense is the best defense."
    ),
    5634: (
        "A ninja Digimon specializing in stealth. Once called the Silver Crow while serving another Digimon at the "
        "Digital World's creation, it supposedly incurred divine wrath that dyed one wing black."
    ),
    5635: (
        "The strongest Digimon in the Chessmon series, combining extreme range with enormous attack power. "
        "It serves as the dependable protector of the timid KingChessmon."
    ),
    5636: (
        "The Chessmon king plotting to establish a Chessmon Empire, though no other Chessmon knows what that empire "
        "would be and nobody nearby cares. Timid by nature, it is exceptionally fast at running away."
    ),
    5637: (
        "A legendary Digimon born together with Chrono Data through the YMIR Project. "
        "It can enter Holy Mode only when Super Digivolving through the power of sacred light."
    ),
    5638: (
        "A female Demon Lord Digimon wrapped in jet black and known as the Goddess of Darkness. "
        "Its mysterious beauty bewilders victims and ultimately leads them to their deaths."
    ),
    5639: (
        "Flaremon's Mega form, radiating a fiery aura and overwhelming majesty. Its signature Sol Blaster focuses "
        "power into the flame sphere on its back, then fires a sun-shaped orb of searing heat."
    ),
    5640: (
        "Crescemon's Mega form, possessing a mysterious, moonlike presence that captivates all who see it. "
        "Its Crescent Haken slices enemies with its weapon, then confuses them through lunar illusions."
    ),
    5641: (
        "A lotus-like Fairy Digimon called the flower blooming in heaven. Quiet and refined, it grants happy dreams, "
        "but passes devastating judgment upon anyone who acts against its will."
    ),
    5642: (
        "Algomon Ultimate's Mega form, a giant Digimon with greatly amplified close-combat ability. "
        "The eyes across its body release destructive beams powerful enough to distort dimensions."
    ),
    5643: (
        "A brave woman warrior reminiscent of the Amazons of Greek myth. Called the Snake Princess for its snakeskin, "
        "it effortlessly swings Olympia, a greatsword nearly as tall as Minervamon, with one hand."
    ),
    5644: (
        "One of the thirteen Royal Knights. A brilliant strategist and commander, it also displays rare swordsmanship "
        "in direct combat. It can transform into the beastlike Leopard Mode."
    ),
    5645: (
        "A Dinosaur Digimon inhabiting jungles. The blades on its back provide excellent offense and defense, "
        "leaving enormous wounds on anything it attacks."
    ),
    5646: (
        "One of the Olympos XII and the fastest Digimon in the Digital World. The naked eye cannot follow it, "
        "and every recorded image is said to show only an afterimage."
    ),
    5647: (
        "A Dragon Man Digimon discovered in an Eastern computer and believed to be a Greymon subspecies. "
        "Much of its strength remains unknown. Its sword Kikurin slices everything touched by the trail it leaves."
    ),
    5648: (
        "A Demon Beast Digimon regarded as the king of vampire Digimon. GrandDracumon's voice can charm others "
        "and has caused many Angel Digimon to fall. It is also said to possess an immortal body."
    ),
    5649: (
        "The Wind warrior among the Ten Legendary Warriors who saved the ancient Digital World. "
        "One of the earliest Mega Digimon, it possesses golden wings and a shining golden form."
    ),
    5650: (
        "The Light warrior among the Ten Legendary Warriors who saved the ancient Digital World. "
        "One of the earliest Mega Digimon, it was known as the radiant supreme beast."
    ),
    5651: (
        "The Ice warrior among the Ten Legendary Warriors who saved the ancient Digital World. "
        "One of the earliest Mega Digimon, it possessed the strength and courage to thrive in lands of extreme cold."
    ),
    5652: (
        "The Fire warrior among the Ten Legendary Warriors who saved the ancient Digital World. "
        "One of the earliest Mega Digimon, legend grants it strength beyond modern Mega forms."
    ),
    5653: (
        "The Water warrior among the Ten Legendary Warriors who saved the ancient Digital World. "
        "One of the earliest Mega Digimon, it ruled the entire Net Ocean and controlled currents, tsunamis, and all water."
    ),
    5654: (
        "The Steel warrior among the Ten Legendary Warriors who saved the ancient Digital World. "
        "One of the earliest Mega Digimon, AncientWisemon is said to know absolutely everything."
    ),
    5655: (
        "The Darkness warrior among the Ten Legendary Warriors who saved the ancient Digital World. "
        "One of the earliest Mega Digimon, it was born from darkness and governs ruin and annihilation."
    ),
    5656: (
        "The Wood warrior among the Ten Legendary Warriors who saved the ancient Digital World. "
        "One of the earliest Mega Digimon, it is the largest Ancient Digimon and contains many mechanisms within its body."
    ),
    5657: (
        "The Thunder warrior among the Ten Legendary Warriors who saved the ancient Digital World. "
        "One of the earliest Mega Digimon, its form combines many insects, including rhinoceros and stag beetles."
    ),
    5658: (
        "The Earth warrior among the Ten Legendary Warriors who saved the ancient Digital World. "
        "One of the earliest Mega Digimon, it possesses the greatest raw power among the Ancient Digimon."
    ),
    5659: (
        "A legendary Holy Knight Digimon appearing only in an ancient Digital World prophecy. "
        "Its arm-mounted V-Bracelets deploy both weapons and shields."
    ),
    5660: (
        "The most courteous of the Royal Knights. Its policy is to fight every enemy one-on-one, "
        "and the stronger its opponent, the greater its joy."
    ),
    5661: (
        "One of the Seven Great Demon Lords, resembling a long-bearded old man. "
        "Obsessed with every treasure on the network, it cruelly kills Digimon to claim their riches."
    ),
    5662: (
        "A Cyborg Digimon guarding the mysterious Royal Base. It boasts extraordinary stamina "
        "and never stops moving during battle."
    ),
    5663: (
        "A wyvern-powered member of the holy Royal Knights. Its fierce draconic strength and high-purity "
        "Chrome Digizoid dragon armor grant it unrivaled might."
    ),
    5664: (
        "A Holy Knight Digimon and member of the Royal Knights. It can be coldhearted in carrying out missions "
        "and shows no mercy toward the weak."
    ),
    5665: (
        "A Holy Dragon Knight and member of the Royal Knights. Its data volume is so enormous that "
        "older digital hardware cannot render its complete form."
    ),
    5666: (
        "An Ice Digimon that inherited all ten Legendary Warriors' powers and surpassed legend. "
        "By flapping the right-hand ice mass KakiKaki-kun and left-hand KochiKochi-kun, it can apparently fly briefly."
    ),
    5667: (
        "One of the thirteen Royal Knights, born from the fusion of WarGreymon and MetalGarurumon. "
        "Combining both Digimon's traits allows it to display its abilities under any circumstances."
    ),
    5668: (
        "Imperialdramon Dragon Mode's mode-changed Ancient Dragon Man form. Its humanoid body controls its full power "
        "more effectively and equips a Positron Laser on the right arm."
    ),
    5669: (
        "Imperialdramon Fighter Mode's final form, empowered by Omnimon. Said to have stopped a great destruction "
        "in the ancient Digital World, it carries the ultimate sword Omega Blade."
    ),
    5670: (
        "A Holy Knight Digimon bearing a DigiCore that seals the Digital Hazard. Ten pure-white wings rise behind "
        "its crimson armor. It carries divine lance Gungnir and divine sword Blutgang."
    ),
    5671: (
        "A special colossal Digimon born from a giant DigiEgg created when many malicious Kuramon, "
        "the In-Training basis of Diaboromon, gathered and fused."
    ),
    5672: (
        "A high-level Demon Lord Digimon born by controlling overflowing power through an evil heart. "
        "Myotismon's final form, it successfully surpasses VenomMyotismon while retaining intelligence."
    ),
    5673: (
        "A dark entity born from the combined negative emotions of humans and Digimon, said to bring great ruin. "
        "It controls endlessly expanding darkness and reshapes countless tentacles to wield accumulated power."
    ),
    5674: (
        "A Wicked God Digimon said to be the defeated Millenniummon revived after gaining a dark soul. "
        "The final Millenniummon form, it possesses extraordinarily powerful Darkness."
    ),
    5675: (
        "Gallantmon's alternate form after awakening to Virus instincts. Its heart is consumed by darkness, making it "
        "the Digital Hazard itself. Demonic Chrome Digizoid armor accompanies lance Balmung and shield Gorgon."
    ),
    5676: (
        "A legendary Digimon born by gathering every Spirit. It governs rebirth and death, is worshiped as a god of war, "
        "and is said to wield power capable of shaking heaven and earth."
    ),
    5677: (
        "A spiritual Digimon born from the darkness inside Millenniummon's mind. It has no fixed form, changing with "
        "anger and hatred, and possesses the terrifying ability to attack an enemy's mind directly."
    ),
    5678: (
        "A phantom Bird Digimon living in the stratosphere forty kilometers above the ground. Its six giant wings "
        "span thirty meters. Legend calls it an ancient species from the Digital World's creation."
    ),
    5679: (
        "ShineGreymon's special Burst Mode, temporarily unlocking its maximum ability through Burst Digivolution. "
        "A high-energy flame aura comparable to the sun envelops its body."
    ),
    5680: (
        "ShineGreymon's uncontrolled Ruin Mode, caused by Burst Digivolution through dark power. "
        "Its signature Torrid Weiss fires the dark flames surrounding it from its fingertips in indiscriminate attacks."
    ),
    5681: (
        "MirageGaogamon's special Burst Mode, temporarily unlocking its maximum ability. "
        "It wields a planetary-class energy weapon and wears an aura whose energy rivals a planet."
    ),
    5682: (
        "Ravemon's special Burst Mode, temporarily unlocking its maximum ability through Burst Digivolution "
        "and wearing all energy in the atmosphere as an aura."
    ),
    5683: (
        "Rosemon's special Burst Mode, temporarily unlocking its maximum ability through Burst Digivolution "
        "and surrounding itself in an aura of love and beauty."
    ),
    5684: (
        "An unstable Digimon born from DNA Digivolution while retaining both original DigiCores, causing the Digital World "
        "to recognize it as a bug. Chaosmon is the codename given to a Digimon that should not exist."
    ),
    5685: (
        "One of the Four Sovereign Digimon guarding the Digital World. This legendary being protects the East "
        "and releases devastating lightning."
    ),
    5686: (
        "One of the Four Sovereign Digimon guarding the Digital World. This legendary being protects the West "
        "and possesses the Steel attribute."
    ),
    5687: (
        "One of the Four Sovereign Digimon guarding the Digital World. This legendary being protects the South "
        "and commands searing fire."
    ),
    5688: (
        "One of the Four Sovereign Digimon guarding the Digital World. This legendary being protects the North "
        "and freely controls water."
    ),
    5689: (
        "A subspecies born by fusing Plesiomon with Seadramon-family data. "
        "Its radiant golden armor shines with light said to purify every evil."
    ),
    5690: (
        "Chaosdramon is an improved, strengthened Machinedramon with a crimson metal body. "
        "Even the program installed in its DigiCore has been upgraded for greater destruction."
    ),
    5691: (
        "An extremely aggressive Digimon whose passion fuels every attack. No matter how badly its body is damaged, "
        "it never abandons a fight while that passion burns. This is why Shoutmon is considered so combative."
    ),
    5692: (
        "A heavyweight Digimon with metal armor and overwhelming power. Gentle and peace-loving outside conflict, "
        "it becomes a mighty fighter that sweeps enemies away with its powerful arms when battle begins."
    ),
    5693: (
        "A Beast Digimon that usually operates alone rather than in packs. Its forehead drill is hardened hair, "
        "and its high-speed Drill Buster boasts perfect accuracy."
    ),
    5694: (
        "A Digimon specialized for aerial combat, with tight turning ability and effortless high-speed maneuvers. "
        "Moody and showy, it changes its flying style with its feelings, making its condition easy to read."
    ),
    5695: (
        "Cheerful, attention-seeking, and extraordinarily positive, it almost never feels discouraged. "
        "Other Digimon therefore underestimate it, but naturally it does not care at all."
    ),
    5696: (
        "Dorulumon's artillery form and strongest move, compressing and firing all its energy. "
        "Another Digimon must aim it accurately, making this great technique possible only through trust between partners."
    ),
    5697: (
        "Ballistamon's reinforced armor form. Housing another Digimon grants that partner several times the strength "
        "and defense, while combining both Digimon's potential produces many powerful special moves."
    ),
    5698: (
        "Starmon and the Pickmons' sword-fusion form. Its sawlike blade cuts by grinding through targets, "
        "shredding the wound so badly that recovery takes longer and damage becomes more severe."
    ),
    5699: (
        "Sparrowmon's supersonic cruising form. Its tremendous thrust allows it to carry other Digimon in flight, "
        "but anyone without exceptional determination is blown away by the wind speed."
    ),
    5700: (
        "A miraculous Victory Form born from four Digimon's absolute determination to win. "
        "Its power is supreme, placing it unquestionably among the strongest Digimon."
    ),
    5701: (
        "A Tyrannosaurus-type Dinosaur Digimon specialized for offense. Its combat instincts are so fierce that it "
        "never stops until the enemy is annihilated. Ordinary Digimon cannot even approach its intimidating aura."
    ),
    5702: (
        "A bird-of-prey Flying Digimon that observes the battlefield from above and excels at precise support attacks. "
        "It is calm, calculating, and exceptionally decisive."
    ),
    5703: (
        "A tactical enhancement form combining Greymon's power with MailBirdramon's armor. "
        "It strengthens Greymon without compromising the original's combat ability."
    ),
    5704: (
        "DeadlyAxemon's elder-brother figure, a knight skilled in dirty tricks. It values victory above everything "
        "and willingly uses any underhanded method during the process."
    ),
    5705: (
        "SkullKnightmon's younger-brother figure, a sturdy fighter with swift movement and seemingly endless stamina. "
        "Fiercely loyal, it trusts its brother and fights for victory. At top speed it leaves afterimages, earning the name Running Lightning."
    ),
    5706: (
        "DarkKnightmon is the fusion of SkullKnightmon and DeadlyAxemon. The elder brother's cunning and the younger's "
        "mobility form a first-rate warrior that still uses dirty methods whenever they help achieve its objective."
    ),
    5707: (
        "A timid but lively and mischievous Fairy Digimon from cold regions. It can heal injuries and sometimes approaches "
        "wounded Digimon unnoticed, quietly treating them before disappearing."
    ),
    5708: (
        "A Digimon serving among the Starmons' core members. A Pickmon that breaks from the group's strict hierarchy "
        "and successfully reaches the big leagues can become Starmon and stand on its own."
    ),
    5709: (
        "A ninja Digimon found everywhere, always watching someone as part of its Digimon-watching hobby. "
        "See one and assume thirty are nearby. Through Information Sharing, everything Monitormon sees spreads faster than light."
    ),
    5710: (
        "A festival-loving Digimon that appears whenever commotion begins and raises excitement with a hot rhythm. "
        "Its beat drives listeners wild; if it enters a fight, the conflict can become a disastrous mass brawl."
    ),
    5711: (
        "A short-tempered Digimon angered by trivial things. Its topknot shrinks as rage rises, exploding when fully "
        "retracted into its head. The blast is only firecracker-sized but colorful enough for party entertainment."
    ),
    5712: (
        "A solitary Demon Warrior with terrifying destructive power. Silent and indifferent, it appears calm but loves "
        "battle more than anyone. Considered among the strongest Digimon, only fools challenge Beelzemon on sight."
    ),
}

assert set(_BATCH_4C) == set(range(5629, 5713))
for _global_record, _localized_text in _BATCH_4C.items():
    if _global_record <= 5637:
        _override_key = (3, 2, 91 + (_global_record - 5629))
    else:
        _override_key = (3, 3, _global_record - 5638)
    OVERRIDES[_override_key] = _localized_text

# Batch 4D: final MESPAK03 encyclopedia records and MESPAK04 effect text.
_BATCH_4D_ENCYCLOPEDIA = {
    5713: (
        "Finalist Form is born when five Digimon unite their hearts. It is the ultimate power-up of the "
        "ground-combat Victory Form after gaining flight capability."
    ),
    5714: (
        "Shinobi Form is Victory Form further empowered by Beelzemon. "
        "With Beelzemon's power added, every technique becomes several times stronger."
    ),
    5715: (
        "A warrior called Physical Form, born from three Digimon's combat instincts. "
        "Its mobile, acrobatic movement confounds enemies, while flexible joints resist impact attacks."
    ),
    5716: (
        "A surviving Weapon Digimon said to save the world in an angel's hands and destroy it in a demon's. "
        "Earnest and hardworking, it overthinks things, struggles under pressure and improvisation, and loves sweets."
    ),
    5717: (
        "A fierce, aggressive little Dragon Digimon most often seen at night. It sings lullabies in a rock style "
        "and has been witnessed performing nightly concerts for Digimon who cannot sleep."
    ),
    5718: (
        "An offense-focused Tyrannosaurus-type Digimon with extreme combat instincts that fights until the enemy "
        "is destroyed. Its brighter coloring than ordinary Greymon supposedly reflects absolute confidence in battle."
    ),
    5719: (
        "DeadlyAxemon's elder-brother figure, a cunning knight that values victory above all. "
        "Its blood-red body proves it has survived and won thousands of battles."
    ),
    5720: (
        "A berserker that sacrificed intelligence to heighten combat instinct. Originally lion-shaped, repeated "
        "modification produced its current form. The deadly poison in its claws rots anything they touch."
    ),
    5721: (
        "A warrior Digimon carrying the sword Jatetsufujin-maru. Its true strength lies not in muscle but strategy; "
        "when Tactimon leads an army, victory is said to have already been decided."
    ),
    5722: (
        "A super-heavyweight mineral Digimon clad in crystal armor that regenerates when broken and wielding "
        "high-powered techniques. Its shining body and power inspire it to call itself the most beautiful and noble being."
    ),
    5723: (
        "A female Demon Lord Digimon whose uncanny beauty confuses opponents. "
        "When commanding armies, it reveals a cruel side by mercilessly discarding subordinates who fail."
    ),
    5724: (
        "Born when Greymon and MailBirdramon join three Digimon's Physical Form. "
        "It excels at ultra-high-speed aerial combat, and its blazing form can be felt from kilometers away."
    ),
    5725: (
        "Born when SkullKnightmon and DeadlyAxemon join three Digimon's Physical Form. "
        "It wields the giant Victory Spear and coldly sweeps enemies aside, earning fear as the Halberd Demon."
    ),
    5726: (
        "An Armed Fighter Form created when Weapon Digimon Spadamon joins four Digimon's Victory Form. "
        "It freely controls two weapons, races across the battlefield, and cuts enemies down to seize victory."
    ),
    5727: (
        "Born from Greymon, MailBirdramon, SkullKnightmon, and DeadlyAxemon. "
        "Its giant drill lance and two huge gun barrels resemble a titan's weapon and overwhelm every Digimon."
    ),
    5728: (
        "A small Digimon with fierce spirit, a loud bark, and exceptional running speed. "
        "Built entirely for land, it cannot swim and is sometimes found unconscious after drowning in a puddle."
    ),
    5729: (
        "A Cosmic Fighter Form created when Weapon Digimon Spadamon adds power to five Digimon's Finalist Form. "
        "It can fly into space and absorb cosmic energy directly into its body."
    ),
    5730: (
        "An artificial Digimon made by packing other Digimon's energy into a special rubber body. "
        "Like a machine, it only performs orders and cannot take any action on its own."
    ),
    5731: (
        "A Digimon that hides underwater or behind rocks and rarely moves. "
        "It will not attack unless approached, but multiplies abnormally when the temperature exceeds 30 degrees."
    ),
}
OVERRIDES.update({
    (3, 3, 75 + (_global_record - 5713)): _localized_text
    for _global_record, _localized_text in _BATCH_4D_ENCYCLOPEDIA.items()
})

_BATCH_4D_ENTRY0 = [
    "HP recovery\nDescription text",
    "MP recovery\nDescription text",
    "Paralysis recovery\nDescription text",
    "Sleep recovery\nDescription text",
    "Confusion recovery\nDescription text",
    "Blind recovery\nDescription text",
    "Full recovery\nDescription text",
    "Complete recovery\nDescription text",
    "Revival\nDescription text",
    "Gate Disk\nDescription text",
    "DigiMemory\nDescription text",
    "Temporary weapon\nDescription text",
    "Temporary armor\nDescription text",
    "Goods test\nDescription text",
    "Score test 0\nDescription text",
    "Score test 1\nDescription text",
    "Score test 2\nDescription text",
    "Score test 3\nDescription text",
    "Score test 4\nDescription text",
    "Score test 5\nDescription text",
    "Score test 6\nDescription text",
    "Score test 7\nDescription text",
    "Score test 8\nDescription text",
    "Score test 9\nDescription text",
    "Score test 10\nDescription text",
    "Key-item test\nDescription text",
    "Has no trait.",
    "Reduces the chance of Paralysis.",
    "Greatly reduces the chance of Paralysis.",
    "Prevents Paralysis.",
    "Slightly reduces Paralysis chance for the whole party.",
    "Reduces Paralysis chance for the whole party.",
    "Slightly increases the chance of Paralysis.",
    "Reduces the chance of Sleep.",
    "Greatly reduces the chance of Sleep.",
    "Prevents Sleep.",
    "Slightly reduces Sleep chance for the whole party.",
    "Reduces Sleep chance for the whole party.",
    "Slightly increases the chance of Sleep.",
    "Reduces the chance of Confusion.",
    "Greatly reduces the chance of Confusion.",
    "Prevents Confusion.",
    "Slightly reduces Confusion chance for the whole party.",
    "Reduces Confusion chance for the whole party.",
    "Slightly increases the chance of Confusion.",
    "Reduces the chance of Blind.",
    "Greatly reduces the chance of Blind.",
    "Prevents Blind.",
    "Slightly reduces Blind chance for the whole party.",
    "Reduces Blind chance for the whole party.",
]

_BATCH_4D_ENTRY1 = [
    "Slightly increases the chance of Blind.",
    "Slightly reduces the chance of Health Down.",
    "Greatly reduces the chance of Health Down.",
    "Prevents Health Down.",
    "Slightly reduces Health Down chance for the whole party.",
    "Reduces Health Down chance for the whole party.",
    "Reduces HP Drain received from enemies.",
    "Greatly reduces HP Drain received from enemies.",
    "Nullifies enemy HP Drain.",
    "Slightly reduces enemy HP Drain for the whole party.",
    "Reduces enemy HP Drain for the whole party.",
    "Increases HP Drain received from enemies.",
    "Reduces MP Drain received from enemies.",
    "Greatly reduces MP Drain received from enemies.",
    "Nullifies enemy MP Drain.",
    "Slightly reduces enemy MP Drain for the whole party.",
    "Reduces enemy MP Drain for the whole party.",
    "Increases MP Drain received from enemies.",
    "Reduces the chance of Shuffle.",
    "Greatly reduces the chance of Shuffle.",
    "Prevents Shuffle.",
    "Slightly reduces Shuffle chance for the whole party.",
    "Reduces Shuffle chance for the whole party.",
    "Slightly increases the chance of Shuffle.",
    "Reduces enemy Poison effects.",
    "Greatly reduces enemy Poison effects.",
    "Nullifies enemy Poison effects.",
    "Slightly reduces enemy Poison effects for the whole party.",
    "Reduces enemy Poison effects for the whole party.",
    "Increases susceptibility to enemy Poison effects.",
    "Reduces the chance of Curse.",
    "Greatly reduces the chance of Curse.",
    "Prevents Curse.",
    "Slightly reduces Curse chance for the whole party.",
    "Reduces Curse chance for the whole party.",
    "Moderately blocks special effects.",
    "Greatly blocks special effects.",
    "Nullifies special effects.",
    "Slightly blocks special effects for the whole party.",
    "Moderately blocks special effects for the whole party.",
    "Slightly increases evasion against enemy attacks.",
    "Greatly increases evasion against enemy attacks.",
    "Slightly reduces evasion against enemy attacks.",
    "Slightly increases attack accuracy.",
    "Greatly increases attack accuracy.",
    "Slightly reduces attack accuracy.",
    "Slightly increases Critical chance.",
    "Greatly increases Critical chance.",
    "Slightly reduces Critical chance.",
    "Slightly increases the success rate of Escape.",
]

_BATCH_4D_ENTRY2 = [
    "Greatly increases the success rate of Escape.",
    "Slightly reduces the success rate of Escape.",
    "Increases the chance of inflicting Paralysis.",
    "Greatly increases the chance of inflicting Paralysis.",
    "Increases the chance of inflicting Sleep.",
    "Greatly increases the chance of inflicting Sleep.",
    "Increases the chance of inflicting Confusion.",
    "Greatly increases the chance of inflicting Confusion.",
    "Increases the chance of inflicting Blind.",
    "Greatly increases the chance of inflicting Blind.",
    "Increases the success rate of HP Drain.",
    "Greatly increases the success rate of HP Drain.",
    "Increases the success rate of MP Drain.",
    "Greatly increases the success rate of MP Drain.",
    "Increases the success rate of Poison.",
    "Greatly increases the success rate of Poison.",
    "Increases the success rate of Curse.",
    "Greatly increases the success rate of Curse.",
    "In battle, slightly increases HP recovery received.",
    "In battle, moderately increases HP recovery received.",
    "In battle, greatly increases HP recovery received.",
    "Increases the amount absorbed by HP Drain.",
    "Greatly increases the amount absorbed by HP Drain.",
    "Increases the amount absorbed by MP Drain.",
    "Greatly increases the amount absorbed by MP Drain.",
    "Slightly increases Poison damage.",
    "Moderately increases Poison damage.",
    "Greatly increases Poison damage.",
    "In battle, slightly reduces MP costs for techniques.",
    "In battle, greatly reduces MP costs for techniques.",
    "Extends the duration of Health Down.",
    "Greatly extends the duration of Health Down.",
    "Slightly increases the chance of turning enemies into melodies.",
    "Moderately increases the chance of turning enemies into melodies.",
    "Greatly increases the chance of turning enemies into melodies.",
    "Increases the enemy item-drop rate after battle.",
    "Greatly increases the enemy item-drop rate after battle.",
    "Slightly increases bits earned after battle.",
    "Moderately increases bits earned after battle.",
    "Greatly increases bits earned after battle.",
    "Slightly increases EXP earned after battle.",
    "Moderately increases EXP earned after battle.",
    "Greatly increases EXP earned after battle.",
    "Massively increases EXP earned after battle.",
    "Increases Expedition success rate.",
    "Greatly increases Expedition success rate.",
    "Reduces Expedition success rate.",
    "Increases job success rate.",
    "Greatly increases job success rate.",
    "Reduces job success rate.",
]

_BATCH_4D_ENTRY3 = [
    "Has no field skill.",
    "Automatically breaks large boulders blocking the path.",
    "Automatically cuts down trees blocking the path.",
    "Automatically melts ice blocking the path.",
    "Digs at Dig points to travel underground.",
    "Dives at Dive points to travel underwater.",
    "Test move 1\nDummy text",
    "Test move 2",
    "Raises one ally's Attack and Defense.",
    "Test move 4\nDummy text",
    "Test move 5\nDummy text",
    "Slams the enemy with a punch of burning spirit. May also inflict Confusion.",
    "Swings a McField microphone like a staff in a technique that doubles as a brilliant performance.",
    "Shot Arms. Also drains HP.",
    "Heavy Speaker\nDummy text",
    "Claw and Fang. May also inflict Sleep.",
    "Enlarges the tail drill and creates a giant tornado that blows all nearby enemies away.",
    "Shooting Ore",
    "Meteor Squall. Also lowers Attack.",
    "Xros Four\nDummy text",
    "Charges straight into the enemy at full speed.",
    "Strikes the enemy with highly acidic bubbles and also inflicts Poison damage.",
    "Fires an arrow of water frozen by absolute-zero breath.",
    "Fires countless frozen-water arrows at all nearby enemies.",
    "Breathes a small blizzard that freezes nearby enemies.",
    "Freezes nearby enemies with a bitter blizzard. May also inflict Confusion.",
    "Freezes nearby enemies in an absolute-zero storm. Moderately increases melody-conversion chance.",
    "Fires a clear water bubble at the enemy. May also inflict Sleep.",
    "Breathes a mysterious water bubble containing evolutionary energy. May also inflict Sleep.",
    "Fires a violently swirling current at the enemy.",
    "Fires an ultra-high-speed current at the enemy.",
    "Fires a current powerful enough to shatter rock.",
    "Launches a violently surging tidal wave at the enemy.",
    "Creates a raging tsunami that swallows all nearby enemies.",
    "Swallows all nearby enemies in a legendary big wave.",
    "Slices the enemy with a vacuum blade and a flash of light.",
    "Somersaults into the enemy at light speed. Greatly increases melody-conversion chance.",
    "Strikes the enemy with a light-wrapped sphere of sound.",
    "Strikes nearby enemies with light-wrapped sound spheres. May also inflict Confusion.",
    "Creates a large typhoon and launches it at nearby enemies.",
    "Creates a small typhoon and launches it at nearby enemies.",
    "Creates a giant typhoon and launches it at nearby enemies.",
    "Slices the enemy with a razor-sharp vacuum blade. Also lowers Speed.",
    "Slices nearby enemies with a crescent shock wave. Also lowers Speed.",
    "Spins at light speed and pulverizes the enemy with its claws.",
    "Fires spheres of light energy from both arms.",
    "Fires an enormous flame sphere that burns the enemy away.",
    "Uses lingering flames around its body to launch a fireball.",
    "Launches a fireball that raises a blazing pillar of flame.",
    "Launches a fireball that raises a searing pillar of flame.",
]

_BATCH_4D_ENTRY4 = [
    "Launches a fireball that raises a pillar of magma.",
    "Slices the enemy with sharp claws filled with Fire power.",
    "Slices the enemy with invincible claws filled with Fire power.",
    "Slices the enemy with mighty claws filled with Fire power.",
    "Calls down a meteor swarm that burns all nearby enemies.",
    "Throws a small bomb that explodes on the enemy.",
    "Throws a powerful bomb that explodes on the enemy.",
    "Engulfs the enemy in fire with a powerful missile.",
    "Burns all nearby enemies with powerful missiles.",
    "Slices all nearby enemies with slashes of light.",
    "Slices the enemy with a slash containing sacred power.",
    "Charges a holy sword with electricity and cuts the enemy down. Moderately increases melody-conversion chance.",
    "Fires a small sphere of sacred light.",
    "Fires a beam of light that judges everything.",
    "Blasts nearby enemies with starlight energy. Also lowers Spirit.",
    "Gathers starlight and blasts nearby enemies, also dealing Light damage.",
    "Fires two cross-shaped arrangements of light spheres in succession, also dealing Light damage.",
    "Slices the enemy with Light power and passes sacred judgment.",
    "Slices all nearby enemies together with Light power.",
    "Strikes the enemy with both arms filled with Light power.",
    "Batters the enemy with a radiant sacred fist.",
    "Slams dark lightning into the enemy.",
    "Crushes the enemy with a miniature black hole's gravity. May also inflict Blind.",
    "Slices the enemy with both Pendulum Blades. Greatly increases melody-conversion chance.",
    "Slams a blazing, spiked iron ball into the enemy.",
    "Smashes the enemy with a soul-filled kick. Also lowers Speed.",
    "Crushes the enemy with a kick filled with the light of justice.",
    "Blasts nearby enemies with a sphere of compressed electricity.",
    "Unleashes Fire power to raise one ally's Attack.",
    "Gathers particles of light to raise one ally's Defense and Speed.",
    "Absorbs the power of endlessly flowing time to raise one ally's Attack and Spirit.",
    "Rapidly fires small metal spheres. Also lowers Speed.",
    "Strikes the enemy with a red whip that subdues prey. Also drains HP.",
    "Fires a high-voltage energy sphere. May also inflict Blind.",
    "Glares at all nearby enemies with eyes of darkness.",
    "Slices all nearby enemies together with star-shaped shuriken.",
    "Slices the enemy with a small electrified sickle.",
    "Summons fierce lightning and drops it onto the enemy.",
    "Summons giant lightning and drops it onto all nearby enemies.",
    "Creates countless lightning bolts and drops them onto all nearby enemies.",
    "Fires an electric sphere and slams it into the enemy.",
    "Fires a powerful electric sphere and slams it into the enemy.",
    "Slices the enemy with sharp electrified claws.",
    "Violently slices the enemy with sharp electrified claws.",
    "Strikes the enemy with a confusing electric whip. May also inflict Confusion.",
    "Strikes the enemy with a dangerous electrified whip. Also drains HP.",
    "Pierces the enemy with energy synthesized from digital data. May also inflict Confusion.",
    "Blasts the enemy with a high-voltage electric sphere.",
    "Fires a fiercely burning blue flame sphere. Also lowers Attack.",
    "Incinerates the enemy with a searing destructive beam.",
]

_BATCH_4D_ENTRY5 = [
    "Cuts the enemy apart with a cross-shaped attack.",
    "Bites the enemy with terrifying, razor-sharp fangs.",
    "Twists its body to create a pillar of water that blasts the enemy away.",
    "Slices the enemy like a bite with blade-like upright claws.",
    "Violently slices the enemy with sharply thrust claws. Also lowers Attack.",
    "Swings its claws at wind-cutting speed to slice the enemy.",
    "Violently slices the enemy with majestic, kinglike claws.",
    "Fires a secret fist technique concentrating a beast's power.",
    "Launches an energy wave from a fist filled with beast power.",
    "Drives hard-fisted punches into all nearby enemies.",
    "Strikes the enemy with an ultra-high-speed punch.",
    "Strikes the enemy with a punch that destroys everything.",
    "Curls into a ball and charges the enemy while spinning.",
]

for _entry_index, _texts in enumerate((
    _BATCH_4D_ENTRY0,
    _BATCH_4D_ENTRY1,
    _BATCH_4D_ENTRY2,
    _BATCH_4D_ENTRY3,
    _BATCH_4D_ENTRY4,
    _BATCH_4D_ENTRY5,
)):
    _expected_count = 13 if _entry_index == 5 else 50
    assert len(_texts) == _expected_count
    for _string_index, _localized_text in enumerate(_texts):
        OVERRIDES[(4, _entry_index, _string_index)] = _localized_text


# Batch 4E: the remainder of MESPAK04 entries 5-9 and the opening of entry 10.
_BATCH_4E_ENTRIES = {
    5: {
        13: "Rams all nearby enemies with tremendous force.",
        14: "Rams all nearby enemies at full power. May also inflict Paralysis.",
        15: "Fires a sphere of dark energy at the enemy. May also inflict Blind.",
        16: "Strikes the enemy with an energy sphere formed from dark messengers.",
        17: "Strikes the enemy with an energy sphere filled with dark chaos.",
        18: "Destroys the enemy's data with an arrow wrapped in a dark aura.",
        19: "Destroys the enemy's data with an arrow of darkness.",
        20: "Buries the enemy's data with an arrow of dark chaos.",
        21: "Incinerates all nearby enemies with a barrage of dark energy.",
        22: "Cuts the enemy cleanly in two with a sacred blade.",
        23: "Tears into the enemy with pointed claws of darkness.",
        24: "Tears into the enemy with razor-sharp claws of darkness.",
        25: "Tears into the enemy with deadly claws of darkness.",
        26: "Slashes the enemy with a life-stealing katana. Also drains MP.",
        27: "Cuts the enemy with a slash filled with chaotic power. May also inflict Blind.",
        28: "Cuts the enemy with a slash filled with jet-black power.",
        29: "Throws incredibly foul poop at the enemy. May also inflict Blind.",
        30: "Creates a purifying barrier that raises all allies' Attack and Spirit.",
        31: "Bathes all nearby enemies in a pyramid's mystic light. May also inflict Blind.",
        32: "Spits bubbles of light from its mouth at the enemy.",
        33: "Spits bubbles of darkness from its mouth at the enemy.",
        34: "Drives needles of lightning energy into the enemy.",
        35: "Fires a fiercely burning sphere of blue flame at the enemy.",
        36: "Slams a spiked iron ball into the enemy.",
        37: "Fires a bullet of electrical energy at the enemy.",
        38: "Hurls a dark shuriken straight at the enemy.",
        39: "Drops blue lightning onto the enemy from above.",
        40: "Uses the power of fire to raise one ally's Attack and Spirit.",
        41: "Uses powerful fire to greatly raise one ally's Attack and Spirit.",
        42: "Uses raging fire to sharply raise one ally's Attack and Spirit.",
        43: "Uses the power of water to raise one ally's Defense.",
        44: "Uses powerful water to greatly raise one ally's Defense.",
        45: "Uses raging water to sharply raise one ally's Defense.",
        46: "Uploads a cursed program into the enemy. May also inflict Confusion.",
        47: "Uses light to raise one ally's Speed.",
        48: "Uses powerful light to greatly raise one ally's Speed.",
        49: "Uses brilliant light to sharply raise one ally's Speed.",
    },
    6: {
        0: "Ensnaring words affect all nearby enemies. May also inflict Confusion.",
        1: "Reads the enemy's intentions and adapts, raising one ally's Defense and Speed.",
        2: "Fires a bolt of highly compressed electrical energy at the enemy.",
        3: "Cuts the enemy repeatedly in a whirling dance. Also deals Dark damage.",
        4: "Impales the enemy with the demonic spear Balmung. Also deals Dark damage.",
        5: "Pummels the enemy with flaming punches and kicks. Also deals Fire damage.",
        6: "Releases alluring energy at all nearby enemies. May also inflict Confusion.",
        7: "Engulfs all nearby enemies in a sinister mist. Also deals Poison damage.",
        8: "Scatters potent poison powder at the enemy. Also deals Poison damage.",
        9: "Fires mysterious rays from its eyes at all nearby enemies.",
        10: "Dances while scattering sweet-smelling pollen. May also inflict Confusion.",
        11: "Paralyzes all nearby enemies with a soothing song. May also inflict Sleep.",
        12: "Calls down healing rain to restore all allies' HP.",
        13: "Uses a healing wave to remove Health Down from all allies and restore HP.",
        14: "Uses healing light to restore all allies' HP.",
        15: "Uses machine power to remove Health Down from all allies and restore HP.",
        16: "Uses the earth's healing power to revive all allies.",
        17: "Revives one ally with a light filled with compassion.",
        18: "Embraces one ally to remove Health Down and restore HP.",
        19: "Uses an ocean wave to remove Health Down from all allies and restore HP.",
        20: "Pulls one ally back from death with a hand of darkness.",
        21: "Runs electricity through one ally to restore HP.",
        22: "Uses a healing wind to remove Health Down from all allies and restore HP.",
        23: "Revives one ally with overflowing light.",
        24: "Uses a wave of light to remove Health Down from all allies and restore HP.",
        25: "Uses nanomachines to remove Health Down from all allies and restore HP.",
        26: "Slashes the enemy with the huge shuriken on its back. Also deals Light damage.",
        27: "Cuts the enemy in a cross with two sacred swords.",
        28: "Breathes a fierce stream of fire at the enemy. Also deals Fire damage.",
        29: "Seals all nearby enemies inside a space-time stone. May cause instant death.",
        30: "Radiates waves of light energy at all nearby enemies. Also deals Light damage.",
        31: "Carves up the enemy with a giant anchor. May also inflict Confusion.",
        32: "Melts the enemy with a rainbow heat laser. Also deals Poison damage.",
        33: "Cuts the enemy with two swords at light speed. Greatly raises Melody chance.",
        34: "Freezes all nearby enemies with an absolute-zero blizzard. May inflict Paralysis.",
        35: "Triggers a huge explosion with a fierce flash. May also lower Defense.",
        36: "Swings the crane on its back and slams it into the enemy.",
        37: "Seals all nearby enemies in another dimension and destroys them. May cause instant death.",
        38: "Teleports swords of darkness to impale all nearby enemies.",
        39: "Fires dark arrows from the evil eyes in both hands. May cause instant death.",
        40: "Creates a whirlpool that drags all nearby enemies underwater.",
        41: "Unleashes a dark sphere that annihilates all nearby enemies.",
        42: "Summons a beast from hell to attack the enemy. Also deals Dark damage.",
        43: "Incinerates all nearby enemies with hellfire of vengeance. Also deals Fire damage.",
        44: "Destroys all nearby enemies' data with a cloud of dark gas.",
        45: "Calculates all nearby enemies' coordinates and sends them away. May inflict Confusion.",
        46: "Fires dark matter that erases all nearby enemies. Also deals Dark damage.",
        47: "Mercilessly pierces the enemy with the lance on its right arm.",
        48: "Fires dark bullets from Berenjena. Also deals Dark damage.",
        49: "Buries the enemy beyond space and time. May also inflict Paralysis.",
    },
    7: {
        0: "Fires dark heat rays from both shoulders.",
        1: "Unleashes flames of sacred light at all nearby enemies.",
        2: "Rapidly ages the enemy by accelerating time inside its body. May cause instant death.",
        3: "Fires beams from a sacred shield at all nearby enemies. May cause instant death.",
        4: "Swings its sword to cut with a fiery shock wave. Also deals Fire damage.",
        5: "Engulfs all nearby enemies in the darkness of death. May cause instant death.",
        6: "Sends its familiar Kudagitsune to shred all nearby enemies. Also deals Water damage.",
        7: "Cuts the enemy with the divine sword Blutgang.",
        8: "Sweeps all nearby enemies away with a broom. May also lower Defense.",
        9: "Gathers atmospheric energy and releases it at all nearby enemies. Also deals Fire damage.",
        10: "Fires energy waves from its cannons at all nearby enemies. Also deals Electric damage.",
        11: "Gathers light energy and releases it at all nearby enemies. May also lower Spirit.",
        12: "Burns the enemy with energy fused in both hands. Also deals Fire damage.",
        13: "Amplifies the power of light and releases it at all nearby enemies. Also deals Light damage.",
        14: "Rains light-charged candy onto all nearby enemies. May also inflict Sleep.",
        15: "Charges while wreathed in flames. May also lower Speed.",
        16: "Cuts through all nearby enemies with the sacred Omega Blade.",
        17: "Strikes all nearby enemies with electricity from three arms. Also deals Electric damage.",
        18: "Slams the enemy with an explosive bullet-shaped hammer. Also deals Fire damage.",
        19: "Destroys the enemy's data with a dark computer virus. Also deals Dark damage.",
        20: "Releases all its energy to incinerate the enemy. May cause instant death.",
        21: "Burns all nearby enemies with flames breathed from its mouth.",
        22: "Incinerates the enemy with evil flames from its mouth. May cause instant death.",
        23: "Rams the enemy with a gleaming full-metal body.",
        24: "Detonates sacred energy to mow down all nearby enemies.",
        25: "Fires a giant missile that blasts all nearby enemies. May also lower Speed.",
        26: "Bombards all nearby enemies with shells from its entire body. May also lower Speed.",
        27: "Rains down thorns that pierce all nearby enemies.",
        28: "Fires a sphere of ultra-high-voltage electricity.",
        29: "Gathers electrical power and cuts through the enemy and space itself.",
        30: "Releases all its energy to blast all nearby enemies. Also deals Fire damage.",
        31: "Gathers electrical power in its horns and releases it at all nearby enemies.",
        32: "Fires heat rays that burn away all nearby enemies.",
        33: "Cuts with light-charged blades on both arms. May also lower Speed.",
        34: "Fires energy torpedoes at all nearby enemies. Also deals Fire damage.",
        35: "Cuts with the giant zanbato Ryuzanmaru. Also deals Poison damage.",
        36: "Tears into the enemy with enormous razor-sharp claws. Also deals Fighting damage.",
        37: "Hurls its Battle Axe at all nearby enemies.",
        38: "Cuts through all nearby enemies with the dagger Otoko Damashii. Also deals Fire damage.",
        39: "Fills Mjolnir with the power of water and crushes the enemy.",
        40: "Sharpens the tip of its electrified whip and drives it into the enemy.",
        41: "Binds the enemy and shocks it with intense electricity. May also inflict Paralysis.",
        42: "Hurls a spear of lightning to deliver divine punishment.",
        43: "Hurls a spear filled with the power of darkness.",
        44: "Fires an arrow of light from the sacred bow Muspelheim.",
        45: "Releases high-voltage energy at all nearby enemies.",
        46: "Breathes freezing air that encases the enemy in ice. May also inflict Paralysis.",
        47: "Releases a sphere of dark energy at all nearby enemies.",
        48: "Cuts the enemy with an absolute-zero sword and freezes it solid.",
        49: "Launches a sentient spear charged with water power. Also deals Poison damage.",
    },
    8: {
        0: "Scatters heart-shaped spheres that sap all nearby enemies' will. May inflict Confusion.",
        1: "Cuts with a sacred sword born from its arm bracelet. Also deals Light damage.",
        2: "Sprays mummifying gas at all nearby enemies. Greatly raises Melody chance.",
        3: "Fires an electrified supersonic wave. Also deals Electric damage.",
        4: "Releases waves from the dark shield Gorgon at all nearby enemies. Also deals Poison damage.",
        5: "Releases a sphere of dark energy that blasts all nearby enemies.",
        6: "Sends countless dark bats to ambush all nearby enemies.",
        7: "Unleashes evil spirits to attack all nearby enemies. Also deals Poison damage.",
        8: "Burns all nearby enemies with bat-shaped dark power. May also inflict Blind.",
        9: "Unleashes dark energy to annihilate the enemy. Also deals Electric damage.",
        10: "Attaches a light-sealing talisman and detonates it. May also inflict Paralysis.",
        11: "Fires beams of electrical energy from both hands.",
        12: "Launches homing missiles from its entire body. May also lower Speed.",
        13: "Impales the enemy with the twin Royal Meister swords. Also deals Electric damage.",
        14: "Fires a blade of electrical energy from its arm.",
        15: "Throws and detonates a glove-shaped bomb.",
        16: "Blasts all nearby enemies with the Psycho Blaster on its arm.",
        17: "Releases energy in the shape of a flying dragon's flame.",
        18: "Fires a shock wave of light from the pile bunker on its arm.",
        19: "Fires a laser from high above to burn the enemy. Also deals Fire damage.",
        20: "Throws a dark bomb loaded with a computer virus.",
        21: "Fires dark missiles from both arms and detonates them. Also deals Dark damage.",
        22: "Summons storm clouds and drops lightning on all nearby enemies.",
        23: "Fires a missile from its right arm and engulfs the enemy in flame. May lower Defense.",
        24: "Uses a wave of light to rust all nearby enemies. Also deals Poison damage.",
        25: "Fires a ball of flame from the revolver in its arm. Also deals Fire damage.",
        26: "Fires missiles from both arms to burn the enemy. Also deals Fire damage.",
        27: "Incinerates all nearby enemies with scorching flames.",
        28: "Turns both hands into guns and fires light-energy rounds. Also deals Light damage.",
        29: "Traps all nearby enemies inside an illusion-inducing mist. May inflict Confusion.",
        30: "Summons meteors and rains them down on all nearby enemies.",
        31: "Drives dark power into the enemy with a concealed arm-mounted rapier.",
        32: "Fires electrified petals that cut all nearby enemies. May also lower Defense.",
        33: "Unleashes a devastating torrent of water at all nearby enemies.",
        34: "Cuts all nearby enemies with electrified spider silk. May also lower Speed.",
        35: "Moves with electrical speed and carves up all nearby enemies. May inflict Paralysis.",
        36: "Cuts the enemy with a giant kusarigama filled with dark power.",
        37: "Destroys all nearby enemies' data with vibrations of light.",
        38: "Spins its turbine at high speed and delivers a crushing blow.",
        39: "Slams a giant iron ball into all nearby enemies. Also deals Fighting damage.",
        40: "Charges all nearby enemies with a tackle powerful enough to shatter mountains.",
        41: "Releases compressed energy in a huge explosion. Also deals Water damage.",
        42: "Impales the enemy with a giant horn charged with electricity.",
        43: "Hurls a three-pronged spear charged with water. May also inflict Sleep.",
        44: "Carves up the enemy with sharp claws on both arms.",
        45: "Removes its helmet and swings it at full force. Greatly raises Melody chance.",
        46: "Creates a gale that traps all nearby enemies in a storm. May inflict Confusion.",
        47: "Burns all nearby enemies with flames fired from its chest. Also deals Fire damage.",
        48: "Cuts the enemy with razor-sharp scissors charged with electricity.",
        49: "Spins in a flash and cuts with a sharp axe. Also deals Light damage.",
    },
    9: {
        0: "Dives at high speed and pierces all nearby enemies with its shining horn.",
        1: "Fires every laser at once to burn all nearby enemies. Also deals Poison damage.",
        2: "Brings its beloved giant sword down in a blaze of light.",
        3: "Freezes all nearby enemies with absolute-zero air. May also inflict Paralysis.",
        4: "Bathes all nearby enemies in freezing air generated by its tough fur.",
        5: "Blows the enemy away with a sacred earth-powered tornado. May inflict Paralysis.",
        6: "Crystallizes water to extreme hardness and fires it. Also deals Water damage.",
        7: "Fires electricity from the feathers on its head. May also lower Speed.",
        8: "Strikes all nearby enemies with lightning from Thor Hammer.",
        9: "Fires lightning from the blade on its head at all nearby enemies.",
        10: "Unleashes a summoned evil god's dark power. Moderately raises Melody chance.",
        11: "Spits countless bubbles that engulf all nearby enemies. Also deals Water damage.",
        12: "Crosses its forelegs and cuts with the blade of water they create.",
        13: "Fires a destructive beam of darkness with a mighty roar.",
        14: "Slams a shock wave of light into all nearby enemies. May also lower Speed.",
        15: "Carves up the enemy with an ultra-high-speed vacuum blade of light.",
        16: "Surrounds the enemy at top speed and unleashes a rapid barrage. Also deals Fighting damage.",
        17: "Cuts the enemy with a wave of light energy charged in its mouth.",
        18: "Fires energy from mechanisms across its body. Also deals Electric damage.",
        19: "Launches light-charged feathers with a shock wave.",
        20: "Rakes the enemy with claws concealed inside its hands.",
        21: "Burns all nearby enemies with a legendary demon's power. May also lower Defense.",
        22: "Summons a crystal of light and hurls it at the enemy. May also inflict Paralysis.",
        23: "Cuts down all nearby enemies with a legendary sword of light. Also deals Light damage.",
        24: "Spins its staff to create a tornado that swallows all nearby enemies.",
        25: "Fills its forelegs with sacred energy and releases it. Also deals Dark damage.",
        26: "Rains catastrophic lightning onto all nearby enemies. May also lower Speed.",
        27: "Uses volcanic power to lariat all nearby enemies. May also inflict Paralysis.",
        28: "Gathers energy in its wings and scorches all nearby enemies. Also deals Fire damage.",
        29: "Dashes past at gale speed and cuts the enemy.",
        30: "Unleashes a fierce full-scale barrage at all nearby enemies. Also deals Poison damage.",
        31: "Drives its left-arm claw into the enemy and attacks with a spinning charge.",
        32: "Brings its katana down with a fierce battle cry. May also lower Defense.",
        33: "Unleashes ultra-fast slashes with two katanas. Also deals Fighting damage.",
        34: "Draws a sun with its katana while cutting all nearby enemies. May lower Spirit.",
        35: "Fires a giant rocket launcher that blasts all nearby enemies. Also deals Dark damage.",
        36: "Fires heat rays from its arms to burn all nearby enemies.",
        37: "Launches all nearby enemies with heavy blows, then smashes them down.",
        38: "Incinerates the enemy with an ultra-hot fireball. Also deals Fire damage.",
        39: "Corrodes all nearby enemies with a breath of darkness. May cause instant death.",
        40: "Charges the enemy with its whole body filled with fire. May also lower Spirit.",
        41: "Strikes the enemy with a giant electrified chain.",
        42: "Violently tears into the enemy with steel-hard claws.",
        43: "Ambushes all nearby enemies with a mysterious electrified mist. May inflict Confusion.",
        44: "Blows an electrified kiss that leaves all nearby enemies helpless.",
        45: "Shatters all nearby enemies' minds with mysterious dark power. May inflict Confusion.",
        46: "Carves up the enemy with claws wrapped in scorching flames.",
        47: "Releases a sacred heart that enchants the enemy. May also inflict Confusion.",
        48: "Fires a wave of flame energy from the cannon at its waist.",
        49: "Uses a sword of light to seal all nearby enemies in warped space. May cause instant death.",
    },
    10: {
        0: "Fires a light-charged heart at all nearby enemies. May also inflict Sleep.",
        1: "Transforms a powerful electrical charge into an arrow of light and fires it.",
        2: "Unleashes seven spheres of light to judge all nearby enemies. May also lower Spirit.",
        3: "Covers all nearby enemies in endlessly spreading darkness. Also deals Dark damage.",
    },
}


assert set(_BATCH_4E_ENTRIES) == {5, 6, 7, 8, 9, 10}
assert set(_BATCH_4E_ENTRIES[5]) == set(range(13, 50))
for _entry_index in (6, 7, 8, 9):
    assert set(_BATCH_4E_ENTRIES[_entry_index]) == set(range(50))
assert set(_BATCH_4E_ENTRIES[10]) == set(range(4))
for _entry_index, _strings in _BATCH_4E_ENTRIES.items():
    for _string_index, _localized_text in _strings.items():
        OVERRIDES[(4, _entry_index, _string_index)] = _localized_text


# Batch 4F: the remainder of MESPAK04 entry 10 through entry 14, plus entry 15.
_BATCH_4F_ENTRIES = {
    10: {
        4: "Shatters all nearby enemies' hearts with dark crystals. May inflict Confusion.",
        5: "Uses a ray gun to drain data from the enemy's mind. Also drains MP.",
        6: "Envelops the enemy in a sorrowful cry that breaks its will. May inflict Confusion.",
        7: "Cuts the enemy with a greatsword formed by combining a fiery sword and shield.",
        8: "Releases dark-powered flames at all nearby enemies. Also deals Fire damage.",
        9: "Slams a sphere of light energy into all nearby enemies.",
        10: "Releases a dark aura from its wings at all nearby enemies.",
        11: "Erases all nearby enemies' will with its staff. Greatly raises Melody chance.",
        12: "Unleashes the aura of a fiery lion at all nearby enemies. Also deals Fire damage.",
        13: "Burns all nearby enemies with a scorching sphere of sunlight.",
        14: "Dances while cutting the enemy with Noire Luna. May also inflict Confusion.",
        15: "Cuts the enemy with a hook imbued with lunar mystery. May inflict Confusion.",
        16: "Envelops all nearby enemies in an aura and breaks them down electrically.",
        17: "Wraps the enemy in tentacles and crushes it. May also inflict Paralysis.",
        18: "Destroys all nearby enemies with a dimension-warping beam.",
        19: "Splits the earth with Olympia and destroys the enemy. Also deals Fire damage.",
        20: "Cuts down the enemy with a blade of light. May cause instant death.",
        21: "Burns the enemy with a 100,000-degree beam. May also lower Spirit.",
        22: "Cuts through all nearby enemies with the BAN-TYO Blade.",
        23: "Envelops all allies in Digi Entelecheia's light and restores HP.",
        24: "Rakes the enemy with long light-charged claws. May also inflict Blind.",
        25: "Envelops the enemy in countless leaves and purifies it. May inflict Confusion.",
        26: "Fires a focused round of light energy at the enemy.",
        27: "Rains Pickmons onto all nearby enemies for a prickly assault. Also deals Fighting damage.",
        28: "Summons a blue-flame dragon to incinerate the enemy. May cause instant death.",
        29: "Rakes the enemy with claws charged with the power of light.",
        30: "Strikes the enemy with a fist that shines gold.",
        31: "Rams the enemy while wreathed in flames. May also lower Defense.",
        32: "Burns the enemy with fiery breath.",
        33: "Defeats the enemy with a devastating headbutt.",
        34: "Fires a powerful fireball at the enemy. Also deals Fire damage.",
        35: "Burns all nearby enemies with a breath of crimson flame.",
        36: "Cuts the enemy with a plasma-charged blade. May also lower Speed.",
        37: "Blows away all nearby enemies with a giant tornado.",
        38: "Burns the enemy with an X-shaped energy wave. May also lower Attack.",
        39: "Burns the enemy with a high-temperature heat ray.",
        40: "Incinerates the enemy with ultra-hot flames.",
        41: "Sprays a breath of water from its mouth at the enemy.",
        42: "Cuts the enemy with giant shrimp-like pincers. Also deals Water damage.",
        43: "Strikes the enemy with a brutally cold punch.",
        44: "Controls the weather and slams the enemy with the power of water.",
        45: "Fires an ink-filled sphere at the enemy. May also inflict Blind.",
        46: "Spins its discs to cut through all nearby enemies.",
        47: "Fires pointed horns that explode on impact with the enemy.",
        48: "Throws small blades that skewer the enemy.",
        49: "Rakes all nearby enemies with giant hooked claws.",
    },
    11: {
        0: "Throws an electrically charged flower bud at the enemy.",
        1: "Throws a fireball at the enemy at Mach speed.",
        2: "Sweeps away all nearby enemies with a small tornado.",
        3: "Clubs the enemy with the sturdy Bone Club.",
        4: "Destroys all nearby enemies with an immense shock wave.",
        5: "Pounces and tears into the enemy with razor-sharp teeth.",
        6: "Draws all nearby enemies into a whirlwind of light.",
        7: "Incinerates the enemy with ultra-hot flames. Also deals Fire damage.",
        8: "Spits out a large iron ball to crush the enemy. May also lower Attack.",
        9: "Shoots the enemy with a sacred Vulcan cannon. Also deals Light damage.",
        10: "Crushes all nearby enemies beneath its gigantic body.",
        11: "Bites the enemy with ice-cold fangs. May also lower Defense.",
        12: "Cuts with the demon blade Shishioumaru. Significantly raises Melody chance.",
        13: "Hurls a polluted bubble-like mass at the enemy.",
        14: "Buries the enemy with a sinister beam fired from its mouth.",
        15: "Incinerates the enemy with flames of darkness.",
        16: "Places a powerful curse on the enemy. May cause instant death.",
        17: "Throws a syringe that drains the enemy's blood. Also drains HP.",
        18: "Extends both arms and pierces the enemy with its claws. Also deals Dark damage.",
        19: "Summons storm clouds and strikes all nearby enemies with lightning. Also deals Electric damage.",
        20: "Destroys all nearby enemies' data with its tentacles.",
        21: "Cuts the enemy with a demon blade filled with dark power.",
        22: "Unleashes powerful flames that burn all nearby enemies.",
        23: "Envelops the enemy in sleep-inducing bubbles. May also inflict Sleep.",
        24: "Releases static electricity amplified by its wings. May also inflict Paralysis.",
        25: "Whips the enemy with electrified vines. May also inflict Paralysis.",
        26: "Fires ice-charged arrows at all nearby enemies.",
        27: "Draws its katana in a flash and cuts the enemy.",
        28: "Pierces the enemy with electrified spikes on both arms.",
        29: "Bites with dark-powered venomous fangs. Also deals Poison damage.",
        30: "Extends an electrified arm and impales the enemy. Also drains MP.",
        31: "Fires solar-ray energy as a beam. May also inflict Paralysis.",
        32: "Punches all nearby enemies with the electrified spikes on its arms.",
        33: "Gathers electricity in its horns and fires a plasma sphere.",
        34: "Uses the power of rage to launch a rock from its head.",
        35: "Cuts the enemy with sharp electrified pincers.",
        36: "Wraps the enemy in sticky electric threads. May also lower Speed.",
        37: "Cuts the enemy with sharp electrified claws.",
        38: "Cuts the enemy with red claws filled with dark power.",
        39: "Punches the enemy with tremendous power.",
        40: "Fires dark feathers that cut through all nearby enemies.",
        41: "Burns the enemy with an immensely powerful missile. Also deals Fire damage.",
        42: "Purifies the enemy with shells of righteous light.",
        43: "Incinerates all nearby enemies with a powerful cannon. May also lower Attack.",
        44: "Stops time and electrically disintegrates all nearby enemies. May inflict Paralysis.",
        45: "Electrically disintegrates all nearby enemies with a pulse laser.",
        46: "Fires a compressed-air round from its mouth at the enemy.",
        47: "Shocks the enemy with a heart-shaped blown kiss. May also inflict Confusion.",
        48: "Fires a ring of light that purifies the enemy.",
        49: "Throws feather boomerangs that cut through all nearby enemies.",
    },
    12: {
        0: "Fires meteor-like feathers that burn the enemy. Also deals Fire damage.",
        1: "Destroys all nearby enemies with a dark vortex. Also deals Dark damage.",
        2: "Crushes and buries the enemy beneath a gigantic foot.",
        3: "Launches the blades on its back to cut all nearby enemies.",
        4: "Closes in at incredible speed and punches the enemy. Also deals Fighting damage.",
        5: "Burns the enemy with the secret sword Kikurin.",
        6: "Instantly freezes all nearby enemies. Also deals Light damage.",
        7: "Captivates all nearby enemies with darkness. May also inflict Confusion.",
        8: "Single-target HP recovery. Dummy text.",
        9: "Row HP recovery. Dummy text.",
        10: "Strong row HP recovery. Dummy text.",
        11: "Single-target MP recovery. Dummy text.",
        12: "Row MP recovery. Dummy text.",
        13: "Strong row MP recovery. Dummy text.",
        14: "Full recovery. Dummy text.",
        15: "Full recovery. Dummy text.",
        16: "Single-target status recovery. Dummy text.",
        17: "Row status recovery. Dummy text.",
        18: "Revival. Dummy text.",
        19: "All-purpose disc. Dummy text.",
        20: "Stabs the enemy with a fire-charged horn. May also lower Spirit.",
        21: "Burns the enemy with bubbles of intense heat.",
        22: "Bites the enemy with powerful jaws.",
        23: "Cuts the enemy with electrified pincers.",
        24: "Rains slimy liquid onto the enemy. Also deals Poison damage.",
        25: "Throws a life-sized bomb at all nearby enemies.",
        26: "Cuts all nearby enemies with blades of dark wind.",
        27: "Bites and tears into the enemy with sharp fangs.",
        28: "Destroys all nearby enemies with frozen shells.",
        29: "Fires in every direction to burn the enemy. Also deals Fire damage.",
        30: "Purifies all nearby enemies with the divine spear Gungnir.",
        31: "Destroys all nearby enemies with dark-energy rounds. Also deals Poison damage.",
        32: "Engulfs the enemy in painful dark smoke. Also deals Poison damage.",
        33: "Releases all its power to burn all nearby enemies. Also deals Fire damage.",
        34: "Sends all nearby enemies into a dark dimension and destroys them. May cause instant death.",
        35: "Destroys all nearby enemies with lightning from eight dragons. May also lower Speed.",
        36: "Purifies the area with sacred light, raising all allies' Defense and Speed.",
        37: "Burns all nearby enemies in an all-power explosion. Also deals Fire damage.",
        38: "Purifies every enemy with a massive explosion of light.",
        39: "Impales the enemy with a lightning-fast strike.",
        40: "Electrocutes every enemy with a blown kiss. Also lowers Defense.",
        41: "Breaks down all nearby enemies with digital cell rounds.",
        42: "Impales and tears the enemy apart with sharp spikes.",
        43: "Electrocutes all nearby enemies with insect-shaped lightning. May inflict Blind.",
        44: "Punches and slashes all nearby enemies with multiple arms. Also deals Fighting damage.",
        45: "Traps all nearby enemies in a three-dimensional magic circle. May cause instant death.",
        46: "Destroys all nearby enemies with light-energy rounds.",
        47: "Drives an electrified Booster Claw into the enemy.",
        48: "Engulfs all nearby enemies in darkness and destroys them. Also deals Dark damage.",
        49: "Purifies the enemy with a wave of its sacred robe's sleeve.",
    },
    13: {
        0: "Fires needle-like hairs into all nearby enemies. Also deals Poison damage.",
        1: "Strikes the enemy with a whip-like band of electricity. May inflict Confusion.",
        2: "Burns all nearby enemies with demonic hellfire. May cause instant death.",
        3: "Crushes all nearby enemies with a spinning charge. May also lower Speed.",
        4: "Freezes all nearby enemies with refrigerant missiles.",
        5: "Burns the enemy with an energy round. May cause instant death.",
        6: "Purifies the enemy with a strike from the divine spear Gram.",
        7: "Electrocutes the enemy with a smiling headbutt. Also deals Electric damage.",
        8: "Cuts all nearby enemies with a sacred sword. May also lower Spirit.",
        9: "Destroys all nearby enemies with the Behemoth motorcycle. Also deals Dark damage.",
        10: "Knocks the enemy down with an explosive punch.",
        11: "Pierces the enemy with focused light. Moderately raises Melody chance.",
        12: "Freezes all nearby enemies with an ultra-low-temperature blizzard.",
        13: "Burns the enemy with the earth sword GeoGrey Sword.",
        14: "Purifies all nearby enemies with an ultra-heavy strike.",
        15: "Pierces the enemy with a high-speed torrent. May also lower Defense.",
        16: "Electrocutes and cuts the enemy with Ame-no-Ohabari. Also deals Water damage.",
        17: "Purifies the enemy with a one-hit-kill punch.",
        18: "Destroys all nearby enemies with moonlight power. May also inflict Sleep.",
        19: "Sweeps away all nearby enemies with dark energy.",
        20: "Shoots all nearby enemies with small electrified needles.",
        21: "Carves up all nearby enemies with a sharp electric blade.",
        22: "Impales and destroys the enemy with Ambrosius. Also deals Dark damage.",
        23: "Envelops all nearby enemies in a dark sphere. May also inflict Blind.",
        24: "Uses celestial light to restore all allies' HP.",
        25: "Blasts all nearby enemies with dark sand. May also inflict Blind.",
        26: "Strikes with a blood-red electric whip. Also drains MP.",
        27: "Revives one ally with a flower's healing power.",
        28: "Strikes the enemy with a blow filled with a sacred heart.",
        29: "Binds the enemy with dark-powered bandages. May also inflict Paralysis.",
        30: "Breaks down all nearby enemies' data with a beam. Also deals Light damage.",
        31: "Destroys the enemy with a Sanskrit character drawn in dark power.",
        32: "Blasts all nearby enemies with enormous firecrackers.",
        33: "Burns all nearby enemies with a powerful laser.",
        34: "Becomes a dragon of blue light and burns the enemy. Also deals Light damage.",
        35: "Erases all nearby enemies with a purifying roar. May also inflict Paralysis.",
        36: "Fires a spherical plasma round at the enemy. May also lower Speed.",
        37: "Creates a dimensional portal that raises one ally's Defense and Attack.",
        38: "Spins the shuriken on its hands and feet to cut the enemy.",
        39: "Crushes the enemy while discharging electricity violently.",
        40: "Destroys all nearby enemies with stored dark power. May also inflict Sleep.",
        41: "Cuts and purifies the enemy with a single finishing stroke.",
        42: "HP disc for the status screen.",
        43: "MP disc for the status screen.",
        44: "Recovery disc for the status screen.",
        45: "Purifies all nearby enemies with powerful sound waves. May inflict Confusion.",
        46: "Cuts the enemy with electrified claws.",
        47: "Breaks down the enemy with biological missiles from its back. Also deals Fire damage.",
        48: "Breathes dark matter onto the enemy.",
        49: "Draws the Sanskrit character Ra to purify the enemy. May also inflict Blind.",
    },
    14: {
        0: "Punches the enemy with star-shaking light power.",
        1: "Strikes with a blood-soaked whip of darkness. Also drains HP.",
        2: "Kicks the enemy at tremendous speed.",
        3: "Uses an aura to remove Health Down from one ally and restore HP.",
        4: "Engulfs all nearby enemies in dark-matter mist. Also deals Poison damage.",
        5: "Envelops the enemy in bubbles that may inflict Sleep.",
        6: "Suffocates all nearby enemies in bubbles. May also inflict Sleep.",
        7: "Bites the enemy with jaws made of ice.",
        8: "Fires icicles at the enemy. May also lower Defense.",
        9: "Uses its hard shell to raise its own Defense.",
        10: "Cuts the enemy in two with giant pincers. Also deals Water damage.",
        11: "Pierces the enemy with an electrified spear.",
        12: "Uses a special formation to raise all allies' Defense.",
        13: "Destroys the enemy with a small mushroom bomb. Also deals Poison damage.",
        14: "Throws mushroom bombs at all nearby enemies. May also inflict Confusion.",
        15: "Uses celestial light to raise all allies' Speed and Attack.",
        16: "Electrocutes the enemy with Linear Lens beams. May also lower Speed.",
        17: "Strikes the enemy with a mega-powered corkscrew punch.",
        18: "Breathes an unbelievably foul odor at all nearby enemies. May inflict Paralysis.",
        19: "Breathes a sweet scent at all nearby enemies. May also lower Speed.",
        20: "Throws poop at the enemy at tremendous speed. Also deals Dark damage.",
        21: "Throws a massive amount of poop at all nearby enemies. May inflict Confusion.",
        22: "Destroys the enemy from within with ultrasound. May also lower Defense.",
        23: "Shatters the enemy's hearing with a terrible roar. May inflict Confusion.",
        24: "Lulls all nearby enemies to sleep with a beautiful, gentle song.",
        25: "Turns sunlight into arrows and rains them on the enemy. May also lower Spirit.",
        26: "Uses a ward of light to dispel evil, raising all allies' Defense and Spirit.",
        27: "Fires nightmare-inducing sound waves at the enemy. May inflict Paralysis.",
        28: "Torments the enemy with high-frequency sound waves.",
        29: "Fires light-charged body hair at all nearby enemies.",
        30: "Strikes the enemy with an extendable Battle Rod.",
        31: "Rams the enemy with a horn glowing green.",
        32: "Fires light energy gathered in its horn. May also lower Defense.",
        33: "Creates a massive earthquake that destroys all nearby enemies.",
        34: "Crushes the enemy with the Demon Arm on its left side.",
        35: "Charges and blows away all nearby enemies. May also lower Attack.",
        36: "Destroys all nearby enemies with a mighty roar. May inflict Paralysis.",
        37: "Pierces the enemy with a giant drill.",
        38: "Throws a bone stolen from Garurumon at the enemy.",
        39: "Strikes the enemy with spinning drills on both hands.",
        40: "Coats its body in mud to raise its own Defense.",
        41: "Punches with its full weight behind the blow. May also inflict Paralysis.",
        42: "Purifies all nearby enemies with the earth's power. May inflict Paralysis.",
        43: "Breathes dark matter at all nearby enemies. May also lower Defense.",
        44: "Strikes the enemy with two cold tentacles. Also deals Fighting damage.",
        45: "Spins its shell at high speed and charges the enemy.",
        46: "Hides inside its hard shell to raise its own Defense and Spirit.",
        47: "Fires highly compressed water from its head. May also inflict Paralysis.",
        48: "Drives its claws into the enemy and freezes it. May inflict Paralysis.",
        49: "Freezes the enemy with a blast of cold light.",
    },
    15: {
        0: "Fires ice arrows from its wings at all nearby enemies.",
        1: "Fires ultrasonic waves from its mouth at the enemy.",
        2: "Swings its tail like a kick to strike the enemy. May also lower Defense.",
        3: "Cuts the enemy with sharp sickles in both hands.",
        4: "Cuts all nearby enemies with electrified sickles.",
        5: "Cuts the enemy with sharp electrified claws. May also inflict Paralysis.",
        6: "Pierces the enemy with a sharp tail stinger. Also deals Poison damage.",
        7: "Uses a swarm of beetles to obscure all nearby enemies' vision. May lower Attack.",
        8: "Electrocutes all nearby enemies with lightning. May also lower Speed.",
        9: "Releases an electric shock that electrocutes all nearby enemies.",
        10: "Charges all nearby enemies while discharging electricity. May inflict Paralysis.",
        11: "Strikes the enemy with a heavyweight punch. May also lower Speed.",
        12: "Sprays superheated gas that burns the enemy. Also deals Poison damage.",
        13: "Fires a sphere of flame energy at the enemy. May also lower Defense.",
    },
}


assert set(_BATCH_4F_ENTRIES) == {10, 11, 12, 13, 14, 15}
assert set(_BATCH_4F_ENTRIES[10]) == set(range(4, 50))
for _entry_index in (11, 12, 13, 14):
    assert set(_BATCH_4F_ENTRIES[_entry_index]) == set(range(50))
assert set(_BATCH_4F_ENTRIES[15]) == set(range(14))
for _entry_index, _strings in _BATCH_4F_ENTRIES.items():
    for _string_index, _localized_text in _strings.items():
        OVERRIDES[(4, _entry_index, _string_index)] = _localized_text


# Batch 4G: the remainder of MESPAK04 entry 15 through the opening of entry 20.
_BATCH_4G_ENTRIES = {
    15: {
        14: "Moves at high speed to raise its own Defense and Speed.",
        15: "Electrocutes the enemy with a powerful laser.",
        16: "Readies mechanical darts and charges all nearby enemies.",
        17: "Leaps high into the air and stomps the enemy.",
        18: "Fires a flame arrow from its hands. May also lower Defense.",
        19: "Unleashes streams of flame from its fists at all nearby enemies.",
        20: "Strikes the enemy with a flaming whirlwind kick.",
        21: "Makes all nearby enemies' hearts ache with a dark voice. May inflict Sleep.",
        22: "Erases the enemy with a black sphere. May cause instant death.",
        23: "Destroys the enemy with a song pitched like hell. May also inflict Blind.",
        24: "Freezes all nearby enemies with cold breath. May also inflict Paralysis.",
        25: "Impales the enemy with two long fangs. May also inflict Paralysis.",
        26: "Confuses all nearby enemies with sound waves from its horn.",
        27: "Shakes all nearby enemies with ultra-low-frequency sound. It may restore their HP.",
        28: "Commands ferocious plankton to attack all nearby enemies.",
        29: "Charges the enemy like a homing torpedo. May also lower Defense.",
        30: "Breaks down the enemy's data at the nanoscale. May also inflict Confusion.",
        31: "Fires small bombs from its fingertips. May also lower Defense.",
        32: "Strangles and electrocutes the enemy with tentacles. May also lower Speed.",
        33: "Sprays highly toxic ink at all nearby enemies. Also deals Poison damage.",
        34: "Cuts the enemy with giant sickles in both hands. May also lower Attack.",
        35: "Cuts all nearby enemies with sacred vacuum blades.",
        36: "Strikes with a giant electrified hammer. May also inflict Paralysis.",
        37: "Sends an electric shock from Pao Tsu through all nearby enemies.",
        38: "Drags the enemy into the deep sea and suffocates it.",
        39: "Impales the enemy with the beloved harpoon Torrent. May also lower Spirit.",
        40: "Swings a giant horn and slams it into the enemy. May inflict Paralysis.",
        41: "Lowers a giant horn and charges all nearby enemies. May inflict Paralysis.",
        42: "Blasts the enemy with water at tremendous pressure.",
        43: "Destroys all nearby enemies with a giant tsunami. Also deals Water damage.",
        44: "Punches the enemy with a shining fist that explodes. Also deals Fire damage.",
        45: "Releases cosmic energy at all nearby enemies. Also deals Light damage.",
        46: "Throws lightning-fast petals that cut the enemy. May also inflict Blind.",
        47: "Engulfs all nearby enemies in cherry blossoms and brilliant light. May inflict Confusion.",
        48: "Throws a disc of light at the enemy.",
        49: "Fires poop from the Empty-Can Bazooka. May also inflict Sleep.",
    },
    16: {
        0: "Cuts the enemy in half with a chainsaw.",
        1: "Throws a powerful hand grenade at the enemy. May cause instant death.",
        2: "Breathes a stream of fire that burns the enemy.",
        3: "Fires a huge fireball at all nearby enemies.",
        4: "Swings a giant sword to cut the enemy. May also inflict Blind.",
        5: "Splits the ground with a sacred sword and sweeps away all nearby enemies.",
        6: "Uses a magic staff to bewilder the enemy.",
        7: "Fires a giant electric beam at the enemy.",
        8: "Erases the enemy with a magic circle of light.",
        9: "Stands perfectly still while mowing down all nearby enemies.",
        10: "Shoots the enemy with an arm-mounted Gatling gun. Also deals Fire damage.",
        11: "Drives a flaming fist into the enemy. Significantly raises Melody chance.",
        12: "Turns its body into a flaming rocket and crushes the enemy. May lower Defense.",
        13: "Strikes all nearby enemies with a devastating open-palm blow.",
        14: "Strikes all nearby enemies with the sacred Vajra. May also lower Spirit.",
        15: "Knocks all nearby enemies into the gates of hell. Also deals Fire damage.",
        16: "Burns the enemy with a scorching flamethrower. Also deals Fire damage.",
        17: "Fires cold flames of ice at the enemy. Significantly raises Melody chance.",
        18: "Fires ice filled with cold flames at the enemy. Greatly raises Melody chance.",
        19: "Spreads poison mist that blinds all nearby enemies.",
        20: "Drives a venomous tail stinger into the enemy. Also deals Poison damage.",
        21: "Throws a shining jewel at the enemy. May also inflict Sleep.",
        22: "Summons a sacred stone monument that sweeps up all nearby enemies.",
        23: "Destroys all nearby enemies with a red beam. May cause instant death.",
        24: "Punches the enemy with a metallic fist.",
        25: "Makes the enemy slip on a banana peel. May also inflict Confusion.",
        26: "Bites the enemy repeatedly with sharp teeth. May also lower Speed.",
        27: "Destroys all nearby enemies with high-frequency light. May also lower Speed.",
        28: "Sprays grenade rounds at all nearby enemies.",
        29: "Fires a cannon that blasts the enemy.",
        30: "Buries the enemy with a solemn song. May also inflict Sleep.",
        31: "Makes all nearby enemies hear the dead's sorrowful screams. Also deals Electric damage.",
        32: "Charges and impales the enemy with the bones covering its body. May inflict Paralysis.",
        33: "Spins a fin bone and launches it at the enemy. May also inflict Paralysis.",
        34: "Rallies the spirit to raise one ally's Attack.",
        35: "Crushes the enemy with the Queen Stick. May also inflict Confusion.",
        36: "Pierces all nearby enemies' hearts with a mechanical sword.",
        37: "Breaks into a full sprint to raise its own Speed.",
        38: "Orders a shadow warrior to attack with electricity. May also inflict Confusion.",
        39: "Cowers while reluctantly striking all nearby enemies with electricity. May cause instant death.",
        40: "Strikes the enemy with ice covered in red syrup. May also inflict Paralysis.",
        41: "Strikes the enemy with ice covered in blue syrup.",
        42: "Tears through the enemy's armor with mechanical claws.",
        43: "Breaks down all nearby enemies with an energy wave. Also deals Electric damage.",
        44: "Hits the enemy with an intensely numbing feeling. May also inflict Confusion.",
        45: "Throws balls of flame at all nearby enemies.",
        46: "Swings a microphone and clobbers the enemy.",
        47: "Destroys the enemy with immensely powerful arms.",
        48: "Destroys all nearby enemies with sound waves from its speakers.",
        49: "Uses its horn to throw the enemy. Also deals Electric damage.",
    },
    17: {
        0: "Spins the drill on its head and drives it into the enemy.",
        1: "Creates a drill-powered tornado that blows away all nearby enemies. May lower Defense.",
        2: "Rides a spinning drill into the enemy. May also lower Speed.",
        3: "Rams the enemy in a burst of light with a thunderous roar.",
        4: "Cuts the enemy with wings of light while racing past.",
        5: "Rapid-fires plasma lasers at the enemy. Also deals Electric damage.",
        6: "Throws a shining star-shaped boomerang at the enemy.",
        7: "Has a Pickmon army blind the enemy. May also lower Speed.",
        8: "Condenses all its energy and blasts the enemy. May also lower Speed.",
        9: "Fires a Vulcan cannon at the enemy at ultra-high speed.",
        10: "Rushes in while hovering and knocks the enemy away.",
        11: "Fires light energy at the enemy. Also deals Electric damage.",
        12: "Slices through the enemy with a burning blade.",
        13: "Punches the enemy with fighting spirit behind the blow.",
        14: "Cuts all nearby enemies with a burning V-Boomerang.",
        15: "Cuts the enemy in two with the Burning Star Sword. Also deals Fire damage.",
        16: "Slams a blazing tail into all nearby enemies.",
        17: "Leans forward and charges the enemy. May also inflict Paralysis.",
        18: "Sweeps the enemy aside with a long, superheated tail.",
        19: "Approaches silently and drops a bomb of light on the enemy.",
        20: "Spits a high-energy plasma round at the enemy.",
        21: "Destroys the enemy with ultra-hot claws.",
        22: "Flashes the eye on its chest to paralyze all nearby enemies. May lower Defense.",
        23: "Leaps into close range and thrusts with darkness. May cause instant death.",
        24: "Spits powerful digestive fluid at the enemy. May also inflict Poison.",
        25: "Dashes between enemies and cuts them down.",
        26: "Cuts the enemy with an axe carried on its shoulder.",
        27: "Revives the power of the dead to raise its own Defense and Attack.",
        28: "Blocks the enemy's path and delivers a merciless thrust.",
        29: "Holds a hand over the wound to remove Health Down from all allies.",
        30: "Creates a shock wave of light around all nearby enemies. Also deals Light damage.",
        31: "Holds a hand over the wound to restore all allies' HP.",
        32: "Crucifies the enemy in exchange for a wish. May also inflict Blind.",
        33: "Fires a dark beam from a giant gun. Also deals Dark damage.",
        34: "Sweeps away the enemy with a high-powered heat beam.",
        35: "Slams heat energy into all nearby enemies.",
        36: "Becomes a shining meteor and crashes into all nearby enemies.",
        37: "Fires an ultra-powerful dark beam. Also deals Fire damage.",
        38: "Cuts the enemy while bombarding it with light bullets. Also deals Dark damage.",
        39: "Tears into the enemy with venomous sharp claws. May also inflict Poison.",
        40: "Releases lion-shaped dark energy at the enemy. Also deals Dark damage.",
        41: "Strikes the enemy with a devastating headbutt.",
        42: "Hits the enemy with a moderately hot flamethrower.",
        43: "Blows mist that blinds all nearby enemies. May also lower Speed.",
        44: "Rams the enemy without fear of death.",
        45: "Breathes high-temperature air at all nearby enemies.",
        46: "Ji Shurunen. Dummy text.",
        47: "Eucalyptus Claw. Dummy text.",
        48: "Evil Snore. Dummy text.",
        49: "Confuses all nearby enemies with a belly dance. May also lower Spirit.",
    },
    18: {
        0: "Dances close and drains the enemy's blood. Also drains HP.",
        1: "Excrement. Dummy text.",
        2: "Platinum Excrement. Dummy text.",
        3: "Splatter Hunting. Dummy text.",
        4: "Ogre Flame. Dummy text.",
        5: "Cathedral. Dummy text.",
        6: "Aura Dio Grandioloqua. Dummy text.",
        7: "Sprinkles sparkling sweet powder on the enemy.",
        8: "Pokes the enemy with a small thorn-like object.",
        9: "Uses ninjutsu to strike the enemy with a fireball.",
        10: "Shoots the enemy with a ninjutsu water pistol.",
        11: "Uses ninjutsu to summon wind against the enemy.",
        12: "Uses ninjutsu to discharge electricity at the enemy.",
        13: "Plays a fiery rhythm to raise all allies' Attack.",
        14: "Bombards the enemy with shock waves of light.",
        15: "Pummels the enemy with shining drumsticks.",
        16: "Bathes the enemy in the blast from a massive explosion.",
        17: "Explodes and scatters particles at all nearby enemies.",
        18: "Fires a plasma round at the enemy. May also lower Defense.",
        19: "Fires a compressed sphere of light-filled air at the enemy.",
        20: "Turns air into plasma and fires it at all nearby enemies.",
        21: "Strikes the enemy with enough force to cause an earthquake.",
        22: "Buries the enemy with enough power to awaken the dead.",
        23: "Collapses the ground to strike down all nearby enemies.",
        24: "Cuts the enemy in half with planet-destroying force.",
        25: "Launches a crystal at the enemy with a punch.",
        26: "Rolls into a ball and crushes all nearby enemies. May cause instant death.",
        27: "Reflects light to blind all nearby enemies. May also lower Speed.",
        28: "Breathes solar lasers at all nearby enemies. May also inflict Blind.",
        29: "Cuts the enemy with claws that rot whatever they touch.",
        30: "Rams the enemy with its thorn-covered body.",
        31: "Engulfs all nearby enemies in a huge explosion.",
        32: "Rains the blades on its back onto the enemy. Also deals Fighting damage.",
        33: "Fires dark red bubbles from its eyes. May also inflict Confusion.",
        34: "Raises its own Defense with a shining barrier of light.",
        35: "Charges and punches with powerful claws. May also lower Attack.",
        36: "Spits absorbed flames at all nearby enemies. Greatly raises Melody chance.",
        37: "Punches the enemy with shining thoughts of victory.",
        38: "Cuts with hot, powerful foreclaws. May also lower Speed.",
        39: "Spits an iron ball from its mouth at the enemy.",
        40: "Runs a high-voltage current through all nearby enemies.",
        41: "Spits a small fireball from its mouth at the enemy.",
        42: "Spits a sphere of light-filled air. May also inflict Paralysis.",
        43: "Uses a phantom glow to bewilder and poke the enemy. May inflict Confusion.",
        44: "Fires mysterious energy at the enemy. Also drains HP.",
        45: "Cuts the enemy with hard claws.",
        46: "Raises the ground to attack all nearby enemies. May also lower Speed.",
        47: "Sprays water stored in its mouth at the enemy.",
        48: "Commands small fish to attack all nearby enemies.",
        49: "Sends countless bats to attack the enemy. Also drains MP.",
    },
    19: {
        0: "Blasts all nearby enemies with toy missiles.",
        1: "Implants a virus-infected gear in the enemy's body. May also inflict Blind.",
        2: "Destroys the enemy with a sacred high-pitched cry. May inflict Paralysis.",
        3: "Spits electrified needle-like threads at the enemy. May inflict Paralysis.",
        4: "Pecks the enemy fiercely like a woodpecker. May also lower Attack.",
        5: "Curls into a ball and charges all nearby enemies. May also lower Attack.",
        6: "Spits a sphere of hot air from its mouth at the enemy.",
        7: "Spits a sphere of cold air from its mouth at the enemy.",
        8: "Unleashes powerful palm strikes at all nearby enemies.",
        9: "Summons dark ice and hurls it at all nearby enemies. May also lower Spirit.",
        10: "Breathes poison mist at all nearby enemies. May also inflict Poison.",
        11: "Swiftly rakes all nearby enemies with wing claws.",
        12: "Throws a giant fireball at all nearby enemies.",
        13: "Fires a hard black sphere at the enemy.",
        14: "Scatters allergenic pollen at all nearby enemies. May inflict Confusion.",
        15: "Spits hard fruit seeds at the enemy. Also deals Light damage.",
        16: "Leaps in close and uppercuts the enemy. May also inflict Paralysis.",
        17: "Crashes into the enemy while spinning with sacred power.",
        18: "Charges headfirst in its helmet through all nearby enemies.",
        19: "Destroys all nearby enemies with the evil eyes in both hands. May inflict Paralysis.",
        20: "Raises its shield and charges straight at the enemy. May inflict Paralysis.",
        21: "Throws a poison-mushroom bomb at the enemy.",
        22: "Releases electricity stored between its pincers. May inflict Paralysis.",
        23: "Punches the enemy with a fist heated by fire.",
        24: "Gathers power in its head and fires a water sphere. May also inflict Sleep.",
        25: "Cuts with a sacred katana that chirps cheerfully. May also inflict Blind.",
        26: "Rams the enemy with its soft, bouncy body.",
        27: "Fires a small arrow of ice at the enemy.",
        28: "Pierces the enemy with a sacred spear that explodes on contact.",
        29: "Throws Thor Hammer at all nearby enemies.",
        30: "Pummels the enemy repeatedly with its big ears. Also deals Fighting damage.",
        31: "Fires ultra-high-pressure water at all nearby enemies.",
        32: "Shoots the enemy with a water-powered guiding arrow.",
        33: "Spins while striking the enemy repeatedly.",
        34: "Glides down from high above and charges the enemy.",
        35: "Cuts all nearby enemies repeatedly at light speed. May inflict Confusion.",
        36: "Throws its shining crest like a boomerang at the enemy.",
        37: "Releases a fierce fiery shock wave at all nearby enemies. May lower Speed.",
        38: "Finely slices the enemy with claws made from digital data.",
        39: "Swallows all nearby enemies in a black hole between its pincers. May inflict Blind.",
        40: "Punches with a fist that explodes on contact. Also deals Fire damage.",
        41: "Sprays machine-gun fire from both arms at all nearby enemies.",
        42: "Cuts with electrified steel claws. May also lower Defense.",
        43: "Summons storm clouds and drops lightning on all nearby enemies. Also deals Light damage.",
        44: "Releases electricity gathered from nature at all nearby enemies.",
        45: "Cuts the enemy in half with giant pincers. May also inflict Paralysis.",
        46: "Fires a powerful plasma-energy cannon. May also lower Defense.",
        47: "Fires scorching arrows from the orbs in both hands. Moderately raises Melody chance.",
        48: "Cuts the enemy in half with a sacred blade.",
        49: "Slams a bean-shaped iron ball into the enemy.",
    },
    20: {
        0: "Annihilates all nearby enemies with a numbing shock wave. May inflict Paralysis.",
        1: "Rakes the enemy with falcon-like razor-sharp claws.",
        2: "Gathers power in its head and fires a fireball at the enemy.",
        3: "Slips inside the enemy's guard and delivers an uppercut.",
        4: "Mows down all nearby enemies like a wild beast.",
        5: "Retracts its limbs into a cocoon and charges the enemy.",
        6: "Creates a tsunami that freezes all nearby enemies. May inflict Paralysis.",
        7: "Entangles the enemy in a sinister web-like membrane. May also inflict Sleep.",
        8: "Buries all nearby enemies with a seductive dark kiss. May inflict Paralysis.",
        9: "Melts into all nearby enemies' shadows and immobilizes them. May lower Speed.",
        10: "Swiftly swings a demon blade to cut the enemy in a cross. Also deals Dark damage.",
        11: "Kicks filthy liquid onto the enemy. May also inflict Confusion.",
        12: "Buries the enemy in a golden radiance.",
        13: "Sprays fine needles across the enemy's entire body.",
        14: "Breathes blue flames from its mouth at the enemy.",
        15: "Fires Vulcan cannons from both hands at all nearby enemies.",
        16: "Fires a legendary energy round at the enemy.",
        17: "Cuts all nearby enemies with sacred blades on both ears.",
        18: "Triggers a huge explosion with hard fruit. Also deals Fire damage.",
        19: "Restores one ally's HP with a drop of life.",
        20: "Transforms into a wooden mallet and delivers sacred judgment. May cause instant death.",
        21: "Slams its body down to cause an earthquake around all nearby enemies.",
        22: "Breathes intense flames that burn all nearby enemies.",
        23: "Blinds all nearby enemies with light from its earrings. May also lower Spirit.",
        24: "Drives a Mach-speed jab into the enemy. Also deals Fighting damage.",
        25: "Charges and crushes the enemy with a giant horn. May inflict Paralysis.",
    },
}


assert set(_BATCH_4G_ENTRIES) == {15, 16, 17, 18, 19, 20}
assert set(_BATCH_4G_ENTRIES[15]) == set(range(14, 50))
for _entry_index in (16, 17, 18, 19):
    assert set(_BATCH_4G_ENTRIES[_entry_index]) == set(range(50))
assert set(_BATCH_4G_ENTRIES[20]) == set(range(26))
for _entry_index, _strings in _BATCH_4G_ENTRIES.items():
    for _string_index, _localized_text in _strings.items():
        OVERRIDES[(4, _entry_index, _string_index)] = _localized_text


# Batch 4H: the remainder of MESPAK04 entry 20 through the opening of entry 27.
_BATCH_4H_ENTRIES = {
    20: {
        26: "Freezes the enemy in place with a piercing red-eyed glare.",
        27: "Bombards the enemy with guided missiles. Also deals Fire damage.",
        28: "Lowers its fangs and charges the enemy. Moderately raises Melody chance.",
        29: "Moves at light speed to raise its own Speed.",
        30: "Blasts the enemy with an electric-energy cannon. May also lower Speed.",
        31: "Summons a meteor to strike the enemy. May also lower Defense.",
        32: "Slams countless wet tentacles into all nearby enemies. May lower Defense.",
        33: "Freezes the enemy with an icy blizzard.",
        34: "Arches its back like a mountain, raising one ally's Defense and Attack.",
        35: "Fires a sphere of scorching magma at the enemy.",
        36: "Bombards all nearby enemies with guided missiles.",
        37: "Blasts the enemy with a concentrated energy cannon.",
        38: "Charges the enemy at full speed. May also inflict Paralysis.",
        39: "Buries all nearby enemies with seductive dark breath. May cause instant death.",
        40: "Sweeps away all nearby enemies with sacred light. Also deals Water damage.",
        41: "Breaks through all nearby enemies with a sacred ultimate dance.",
        42: "Impales the enemy with the divine sword Blutgang.",
        43: "Fires an immensely destructive sword of light. Also deals Dark damage.",
        44: "Cuts the enemy with a crescent-shaped energy naginata.",
        45: "Rains fiery meteors onto all nearby enemies.",
        46: "Uses atmospheric energy to blast all nearby enemies.",
        47: "Clenches a fireball in its fist and punches the enemy.",
        48: "Freezes moisture in the air and hurls it at the enemy.",
        49: "Pierces the enemy with a lightning-sharp kick.",
    },
    21: {
        0: "Annihilates the enemy with a burst of divine light.",
        1: "Strikes the enemy unnoticed, like a shadow creeping closer.",
        2: "Slams the enemy down with battle-kenpo movements.",
        3: "Punches the enemy with a fist wrapped in fire.",
        4: "Punches the enemy with a fist encased in ice.",
        5: "Punches the enemy with an electrified fist.",
        6: "Punches the enemy with a fist wrapped in light.",
        7: "Punches the enemy with a fist wrapped in darkness.",
        8: "Punches the enemy with a tightly clenched fist.",
        9: "Breathes high-temperature air at all nearby enemies.",
        10: "Breathes a blizzard at all nearby enemies.",
        11: "Breathes an electric shock at all nearby enemies.",
        12: "Breathes brilliant light at all nearby enemies.",
        13: "Breathes pitch-black air at all nearby enemies.",
        14: "Breathes a powerful shock wave at all nearby enemies.",
        45: "Uses solar power to restore all allies' HP.",
        46: "Uses a goddess's power to restore one ally's HP.",
        47: "Slaps the enemy's cheeks furiously with wet wings. Also deals Water damage.",
        48: "Uses heavenly light to remove Health Down from all allies and restore HP.",
        49: "Restores one ally's HP with a drop of life.",
    },
    22: {
        0: "Restores one ally's HP with a drop of life.",
        1: "Restores one ally's HP with a drop of life.",
        2: "Uses a wave to remove Health Down from one ally.",
        3: "Drags all nearby enemies underwater and swallows them.",
        4: "Fires two sharp red vacuum blades. Also deals Fighting damage.",
        5: "Undecided 00. Description text.",
        6: "Undecided 01. Description text.",
        7: "King of Rockers. Dummy text.",
        8: "Undecided 02. Description text.",
        9: "Undecided 03. Description text.",
        10: "Soul Majesty. Dummy text.",
        11: "Restores all allies' HP with super-sweet sugar.",
        12: "Turns a shining aura into a blade and cuts the enemy.",
        13: "Destroys all nearby enemies with a special wave. May inflict Paralysis.",
        14: "Undecided 06. Description text.",
        15: "Undecided 07. Description text.",
        16: "Azure Flame. Dummy text.",
        17: "Undecided 08. Description text.",
        18: "Undecided 09. Description text.",
        19: "Tanz Dammerung. Dummy text.",
        20: "Throws a giant fireball at the enemy.",
        21: "Strikes all nearby enemies with light amplified through a microphone.",
        22: "Swings a microphone wildly and clobbers all nearby enemies.",
        23: "Burns all nearby enemies with a super flamethrower.",
        24: "Slams a blazing tail into all nearby enemies.",
        25: "Leans forward, accelerates, and charges the enemy.",
        26: "Savages the enemy like a bloodthirsty beast.",
        27: "Uses hypnotic waves to lull all nearby enemies to sleep. May lower Speed.",
        28: "Turns its spear into a drill and mercilessly impales the enemy. Also deals Dark damage.",
        29: "Leaps into a fireball and charges the enemy.",
        30: "Releases wings of light to cut the enemy.",
        31: "Bombards all nearby enemies with plasma breath.",
        32: "Mows down the enemy with the Victory Spear.",
        33: "Traps the enemy in an acidic storm that melts it. May also inflict Blind.",
        34: "Riddles the enemy with powerful repeated thrusts. Also deals Dark damage.",
        35: "Blasts the enemy with an aurora-wrapped bullet. May also inflict Paralysis.",
        36: "Fires sacred cutting waves at the enemy in a cross.",
        37: "Turns a blue aura into a blade and cuts all nearby enemies. Also deals Fire damage.",
        38: "Engulfs all nearby enemies in a giant tornado of fire.",
        39: "Fires a dark cannon from a giant gun at all nearby enemies.",
        40: "Charges the enemy with a giant drill lance. Also deals Fighting damage.",
        41: "Fires a vacuum blade of light that cuts the enemy.",
        42: "Cuts all nearby enemies with solar energy.",
        43: "Crushes all nearby enemies with cosmic energy. Also deals Fire damage.",
        44: "Undecided 29. Description text.",
        45: "Undecided 30. Description text.",
        46: "Undecided 31. Description text.",
        47: "Undecided 32. Description text.",
        48: "Undecided 33. Description text.",
        49: "Undecided 34. Description text.",
    },
}

for _index, _size in enumerate(("small", "normal", "large", "giant", "colossal"), 15):
    _BATCH_4H_ENTRIES[21][_index] = (
        f"Spits a {_size} mass of flame at the enemy. Slightly raises Melody chance."
    )
for _index, _size in enumerate(("small", "normal", "large", "giant", "colossal"), 20):
    _BATCH_4H_ENTRIES[21][_index] = (
        f"Throws a {_size} chunk of ice at the enemy. Slightly raises Melody chance."
    )
for _index, _strength in enumerate(("light", "normal", "strong", "powerful", "overwhelming"), 25):
    _BATCH_4H_ENTRIES[21][_index] = (
        f"Sends a {_strength} electric shock through the enemy. Slightly raises Melody chance."
    )
for _index, _strength in enumerate(("faint", "normal", "strong", "powerful", "overwhelming"), 30):
    _BATCH_4H_ENTRIES[21][_index] = (
        f"Destroys the enemy with a {_strength} radiance. Slightly raises Melody chance."
    )
for _index, _strength in enumerate(("faint", "normal", "strong", "powerful", "overwhelming"), 35):
    _BATCH_4H_ENTRIES[21][_index] = (
        f"Buries the enemy in {_strength} dark energy. Slightly raises Melody chance."
    )
for _index, _strength in enumerate(("light", "normal", "strong", "powerful", "overwhelming"), 40):
    _BATCH_4H_ENTRIES[21][_index] = (
        f"Strikes the enemy with a {_strength} blow. Slightly raises Melody chance."
    )

_BATCH_4H_ENTRIES[23] = {
    **{_index: "Sword of Meteor. Dummy text." for _index in range(6)},
    **{_index: "Call. Dummy text." for _index in range(6, 11)},
    11: "Destroys the enemy with giant mechanical claws. Also deals Electric damage.",
    **{_index: "Call. Dummy text." for _index in range(12, 25)},
}


def _digi_xros_attack(name: str, effect: str = "") -> str:
    text = f"DigiXros into {name} and attack."
    return f"{text} {effect}" if effect else text


_BATCH_4H_XROS_FORMS = {
    23: [
        ("Kuramon", "Also deals Water damage."),
        ("Kuramon", "Also deals Water damage."),
        ("Greymon L", ""),
        ("Tyrannomon", ""),
        ("Devimon", "Also deals Dark damage."),
        ("Airdramon", ""),
        ("Kabuterimon", ""),
        ("Kabuterimon", ""),
        ("Garurumon", ""),
        ("Angemon", ""),
        ("Bakemon", "May cause instant death."),
        ("Leomon", ""),
        ("Leomon", ""),
        ("Gekomon", "May also lower Defense."),
        ("Gatomon", "May also inflict Blind."),
        ("ExVeemon", "May also lower Attack."),
        ("Stingmon", ""),
        ("Ankylomon", ""),
        ("Gargomon", "Also deals Light damage."),
        ("Growlmon", "May also lower Speed."),
        ("Kyubimon", "May cause instant death."),
        ("Chrysalimon", ""),
        ("Seasarmon", "May also lower Spirit."),
        ("Aquilamon", ""),
        ("Dorugamon", "May also lower Attack."),
    ],
    24: [
        ("Reptiledramon", ""),
        ("Apemon", ""),
        ("Minotarumon", ""),
        ("Gaogamon", ""),
        ("Coelamon", ""),
        ("Shellmon", "May also inflict Paralysis."),
        ("IceDevimon", "May also inflict Paralysis."),
        ("Dolphmon", ""),
        ("Tankmon", "Also deals Fire damage."),
        ("Musyamon", ""),
        ("Firamon", "May also lower Defense."),
        ("Lekismon", "May also inflict Sleep."),
        ("Buraimon", "Also deals Fighting damage."),
        ("Agunimon", ""),
        ("MetalGreymon L", ""),
        ("Monzaemon", "May also inflict Sleep."),
        ("Megadramon", "Also deals Fire damage."),
        ("Angewomon", ""),
        ("MegaSeadramon", ""),
        ("WereGarurumon", ""),
        ("Myotismon", ""),
        ("LadyDevimon", "May also inflict Blind."),
        ("Blossomon", "May also lower Defense."),
        ("Lillymon", "Also deals Light damage."),
        ("MagnaAngemon", "May cause instant death."),
        ("Paildramon", ""),
        ("Dinobeemon", "May also inflict Paralysis."),
        ("WarGrowlmon", "Also deals Fire damage."),
        ("Rapidmon", "Also deals Light damage."),
        ("Taomon", ""),
        ("Infermon", ""),
        ("Pandamon", ""),
        ("MarineDevimon", "May also inflict Poison."),
        ("Karatenmon", ""),
        ("Kyukimon", ""),
        ("Sinduramon", ""),
        ("DoruGreymon", "Also deals Fighting damage."),
        ("Kimeramon", ""),
        ("Silphymon", ""),
        ("Whamon", "Also deals Water damage."),
        ("Meteormon", "Also deals Light damage."),
        ("Gigadramon", "Also deals Dark damage."),
        ("RiseGreymon", "Also deals Fire damage."),
        ("MachGaogamon", "Also deals Fighting damage."),
        ("Tyilinmon", ""),
        ("Kabukimon", "May also inflict Confusion."),
        ("Cherrymon", "May also inflict Confusion."),
        ("Lucemon FM", ""),
        ("Phantomon", ""),
        ("Vajramon", ""),
    ],
    25: [
        ("AeroVeedramon", "Also deals Light damage."),
        ("GrapLeomon", ""),
        ("Yatagaramon", "Also deals Dark damage."),
        ("RookChessmon", "Also deals Fire damage."),
        ("Flaremon", "Also deals Fire damage."),
        ("Crescemon", "May also inflict Confusion."),
        ("Magnamon", "Also deals Light damage."),
        ("Argomon Ultimate", "May also inflict Paralysis."),
        ("Shakkoumon", "May also lower Spirit."),
        ("SkullBaluchimon", ""),
        ("Grademon", ""),
        ("Wisemon", "May cause instant death."),
        ("Mermaimon", "May also inflict Confusion."),
        ("Butenmon", ""),
        ("Bastemon", "Also drains HP."),
        ("Cerberumon", "Also deals Fire damage."),
        ("HerculesKabuterimon", ""),
        ("SaberLeomon", "May also inflict Poison."),
        ("MetalEtemon", "May also inflict Confusion."),
        ("MagnaAngemon", "May also inflict Confusion."),
        ("GigaSeadramon", "Also deals Fire damage."),
        ("Piedmon", ""),
        ("Piedmon", ""),
        ("Creepymon", "May cause instant death."),
        ("Phoenixmon", "Also deals Light damage."),
        ("Puppetmon", "Also deals Fire damage."),
        ("Rosemon", "May also inflict Confusion."),
        ("WarGreymon", "Also deals Fire damage."),
        ("MetalGarurumon", "May also inflict Paralysis."),
        ("Machinedramon", "Also deals Electric damage."),
        ("Machinedramon", "Also deals Electric damage."),
        ("VenomMyotismon", "Also deals Dark damage."),
        ("Imperialdramon DM", "Also deals Dark damage."),
        ("Seraphimon", "May also lower Spirit."),
        ("HiAndromon", "Also deals Fire damage."),
        ("Devitamamon", ""),
        ("Cherubimon Good", ""),
        ("Gallantmon", "May cause instant death."),
        ("Gallantmon", "May cause instant death."),
        ("MegaGargomon", "May also lower Speed."),
        ("Sakuyamon", "Also deals Water damage."),
        ("Diaboromon", ""),
        ("Neptunemon", "May also inflict Poison."),
        ("Boltmon", ""),
        ("PrinceMamemon", "Also deals Electric damage."),
        ("Ophanimon", "May also inflict Paralysis."),
        ("Zanbamon", "May also inflict Poison."),
        ("Anubismon", "Also deals Dark damage."),
        ("Cannondramon", ""),
        ("Eaglemon", ""),
    ],
    26: [
        ("Dorugoramon", "May also lower Spirit."),
        ("Beelzemon", "Also deals Dark damage."),
        ("BAN Leomon", ""),
        ("Darkdramon", ""),
        ("Goldramon", ""),
        ("MetalSeadramon", ""),
        ("Valkyrimon", ""),
        ("Justimon", ""),
        ("Vikemon", "May also inflict Confusion."),
        ("SkullMammothmon", "May also inflict Paralysis."),
        ("GranKuwagamon", ""),
        ("Pharaohmon", "Greatly raises Melody chance."),
        ("Alphamon", "May also lower Defense."),
        ("Magnadramon", "May also lower Spirit."),
        ("Millenniummon", "Also deals Dark damage."),
        ("Megidramon", "May cause instant death."),
        ("Sleipmon", ""),
        ("ShineGreymon", "Also deals Fire damage."),
        ("MirageGaogamon", ""),
        ("JumboGamemon", "May also lower Defense."),
        ("Ravemon", "Also deals Water damage."),
        ("Chronomon Holy Mode", ""),
        ("Lilithmon", "May cause instant death."),
        ("Apollomon", ""),
        ("Dianamon", "May also inflict Confusion."),
        ("Lotosmon", "Greatly raises Melody chance."),
        ("Minervamon", "Also deals Fire damage."),
        ("Duftmon", "May cause instant death."),
        ("Mercurimon", "Also deals Fighting damage."),
        ("Gaiomon", ""),
        ("GranDracmon", "Also deals Light damage."),
        ("AncientIrismon", "May also inflict Poison."),
        ("AncientGarurumon", "Greatly raises Melody chance."),
        ("AncientMegatheriummon", "May also inflict Paralysis."),
        ("AncientGreymon", "May also lower Defense."),
        ("AncientMermaimon", ""),
        ("AncientWisemon", "May also inflict Confusion."),
        ("AncientSphinxmon", "May cause instant death."),
        ("AncientTroiamon", "May also lower Speed."),
        ("AncientBeetmon", ""),
        ("AncientVolcanomon", "Also deals Fire damage."),
        ("AncientVolcanomon", "Also deals Fire damage."),
        ("UlforceVeedramon", "Also deals Light damage."),
        ("Craniamon", "Also deals Electric damage."),
        ("TigerVespamon", "Also deals Electric damage."),
        ("Examon", "Also deals Fire damage."),
        ("Daipenmon", ""),
        ("Omnimon", ""),
        ("Imperialdramon FM", "May cause instant death."),
        ("Imperialdramon PM", ""),
    ],
    27: [
        ("Gallantmon Crimson Mode", ""),
        ("Armageddemon", "Also deals Fire damage."),
        ("MaloMyotismon", ""),
        ("Apocalymon", "Also deals Dark damage."),
        ("ZeedMillenniummon", "May cause instant death."),
        ("ChaosGallantmon", "May also inflict Poison."),
        ("Susanoomon", "Also deals Light damage."),
        ("Susanoomon", "Also deals Light damage."),
        ("MoonMillenniummon", "May also inflict Confusion."),
        ("Varodurumon", "Also deals Light damage."),
        ("ShineGreymon Burst Mode", "Also deals Fire damage."),
        ("ShineGreymon Ruin Mode", "Also deals Fire damage."),
        ("MirageGaogamon Burst Mode", ""),
        ("Ravemon Burst Mode", "Also deals Dark damage."),
        ("Rosemon Burst Mode", ""),
        ("Chaosmon", ""),
        ("Azulongmon", ""),
        ("Baihumon", "May also inflict Poison."),
        ("Zhuqiaomon", ""),
        ("Ebonwumon", "May also inflict Confusion."),
        ("Aegisdramon", "Also deals Water damage."),
        ("Chaosdramon", "Also deals Electric damage."),
        ("Shoutmon", ""),
        ("Shoutmon", ""),
        ("Dorulu Cannon", "May also lower Speed."),
        ("Shoutmon X2", "Also deals Electric damage."),
        ("Star Sword", ""),
    ],
}

for _entry_index, _forms in _BATCH_4H_XROS_FORMS.items():
    _start_index = 25 if _entry_index == 23 else 0
    for _offset, (_form_name, _effect) in enumerate(_forms):
        _BATCH_4H_ENTRIES.setdefault(_entry_index, {})[_start_index + _offset] = (
            _digi_xros_attack(_form_name, _effect)
        )

assert set(_BATCH_4H_ENTRIES) == set(range(20, 28))
assert set(_BATCH_4H_ENTRIES[20]) == set(range(26, 50))
for _entry_index in range(21, 27):
    assert set(_BATCH_4H_ENTRIES[_entry_index]) == set(range(50))
assert set(_BATCH_4H_ENTRIES[27]) == set(range(27))
for _entry_index, _strings in _BATCH_4H_ENTRIES.items():
    for _string_index, _localized_text in _strings.items():
        OVERRIDES[(4, _entry_index, _string_index)] = _localized_text


# Batch 4I: MESPAK04 entry 27 through the opening of entry 33.
_BATCH_4I_ENTRIES = {
    27: {},
    28: {},
    29: {
        0: "Completely removes Health Down and fully restores one Digimon's HP and MP.",
        1: "Cures Paralysis on one Digimon.",
        2: "Wakes one Digimon from Sleep.",
        3: "Cures Confusion on one Digimon.",
        4: "Cures Blind on one Digimon.",
        5: "Removes Health Down from one Digimon.",
        6: "Removes Health Down from one horizontal row of Digimon.",
        7: "Revives one Digimon that cannot act.",
        8: "Revives one Digimon and fully restores its HP.",
        9: "Instantly transports your team back to its Fort.",
        10: "Use during battle; if you win, the entire team earns bonus EXP.",
        11: "Use during battle; if you win, the entire team earns bonus EXP.",
        12: "Use during battle; if you win, the entire team earns bonus EXP.",
        13: "A completely useless shell. Sells for very little at a shop.",
        14: "A shell with no particular use. Sells for very little at a shop.",
        15: "A shell with no particular use. It can be sold at a shop.",
        16: "A shell with no particular use. Sells for a high price at a shop.",
        17: "A questionable Numemon-shaped ornament. It can be sold at a shop.",
        18: "A Patamon-shaped ornament. Sells for a high price at a shop.",
        19: "An Impmon-shaped ornament. Sells for a very high price at a shop.",
        20: "An Agumon-shaped ornament. Sells for a very high price at a shop.",
        21: "A coin found by an exploration team. Sells for very little at a shop.",
        22: "A coin found by an exploration team. Sells for a high price at a shop.",
        23: "A coin found by an exploration team. Sells for a very high price at a shop.",
        24: "A coin found by an exploration team. Sells for an incredible price at a shop.",
        25: "Data that drifted in from nowhere. It does not seem to have any use.",
        26: "Changes one Digimon's personality to Energetic.",
        27: "Changes one Digimon's personality to Spoiled.",
        28: "Changes one Digimon's personality to Wild.",
        29: "Changes one Digimon's personality to Cool.",
        30: "Changes one Digimon's personality to Selfish.",
        31: "Changes one Digimon's personality to Gentle.",
        32: "Changes one Digimon's personality to Robot.",
        33: "Changes one Digimon's personality to Funky.",
        34: "Leviamon DigiMemory. Description text.",
        35: "Agumon DigiMemory. Disappears after one use in battle.",
        36: "MagnaAngemon DigiMemory. Disappears after one use in battle.",
        37: "Garurumon DigiMemory. Disappears after one use in battle.",
        38: "MagnaAngemon DigiMemory. Disappears after one use in battle.",
        39: "Guilmon DigiMemory. Disappears after one use in battle.",
        40: "Patamon DigiMemory. Disappears after one use in battle.",
        41: "MetalGarurumon DigiMemory. Disappears after one use in battle.",
        42: "Veemon DigiMemory. Disappears after one use in battle.",
        43: "Darkdramon DigiMemory. Disappears after one use in battle.",
        44: "Gatomon DigiMemory. Disappears after one use in battle.",
        45: "Impmon DigiMemory. Disappears after one use in battle.",
        46: "WarGreymon DigiMemory. Disappears after one use in battle.",
        47: "Examon DigiMemory. Disappears after one use in battle.",
        48: "Omnimon DigiMemory. Disappears after one use in battle.",
        49: "A small glove sold at the Penmon Shop.",
    },
}

_BATCH_4I_XROS_FORMS = [
    ("Jet Sparrow", ""),
    ("Shoutmon X4", "Also deals Fire damage."),
    ("Greymon", "May also inflict Paralysis."),
    ("MetalGreymon", "May also inflict Poison."),
    ("SkullKnightmon", "May cause instant death."),
    ("DarkKnightmon", ""),
    ("Beelzemon", "Also deals Dark damage."),
    ("Beelzemon", "Also deals Dark damage."),
    ("Shoutmon X5", ""),
    ("Shoutmon X4B", "Also deals Dark damage."),
    ("Shoutmon X3", ""),
    ("Spadamon", "May also inflict Paralysis."),
    ("Shoutmon X3GM", ""),
    ("Shoutmon X3SD", "Also deals Dark damage."),
    ("Shoutmon X4S", "Also deals Fire damage."),
    ("GreyKnightsmon", "Also deals Fighting damage."),
    ("Shoutmon X5S", "Also deals Fire damage."),
]
for _offset, (_form_name, _effect) in enumerate(_BATCH_4I_XROS_FORMS, 27):
    _BATCH_4I_ENTRIES[27][_offset] = _digi_xros_attack(_form_name, _effect)

_BATCH_4I_DUMMY_MOVES = [
    "Flame Pillar",
    "Volcano Bomb",
    "Heavy Dragon Magma",
    "Rage Flame",
    "Pressure Aqua",
    "Icicle Bomb",
    "Heavy Hard Rain",
    "Rage Blizzard",
    "Magne Wave",
    "Spark Bomb",
    "Heavy Magne Power",
    "Rage Lightning",
    "Rising Laser",
    "Shining Bomb",
    "Heavy Wind",
    "Rage Tornado",
    "Darkness Eddy",
    "Evil Data Bomb",
    "Heavy Gravity",
    "Rage Demon Breath",
    "Sonic Kick",
    "Mega Knuckle Bomb",
    "Heavy Giga Upper",
    "Rage Grapple",
    "Sword Masquerade",
    "Rainbow Hand",
    "Malkuth Crystal",
    "Hell & Thunder",
    "Heaven & Break",
    "Ice & Fire",
    "Infinity Sword Rain",
    "Omega Death Blade",
    "Data to Data",
    "Tri-Blizzard",
    "Sigma Grapple",
    "Omega Crusher",
    "Chrono DSR",
    "Origin Nebula",
]
for _offset, _move_name in enumerate(_BATCH_4I_DUMMY_MOVES, 44):
    _entry_index, _string_index = divmod(_offset, 50)
    _BATCH_4I_ENTRIES.setdefault(27 + _entry_index, {})[_string_index] = (
        f"{_move_name}. Dummy text."
    )

_BATCH_4I_ENTRIES[28].update({
    32: "Restores a small amount of HP to one Digimon.",
    33: "Restores a moderate amount of HP to one Digimon.",
    34: "Restores a large amount of HP to one Digimon.",
    35: "Restores a great amount of HP to one Digimon.",
    36: "Restores a small amount of HP to one horizontal row of Digimon.",
    37: "Restores a moderate amount of HP to one horizontal row of Digimon.",
    38: "Restores a large amount of HP to one horizontal row of Digimon.",
    39: "Restores a great amount of HP to one horizontal row of Digimon.",
    40: "Restores a slight amount of HP to one Digimon.",
    41: "Restores a small amount of MP to one Digimon.",
    42: "Restores a moderate amount of MP to one Digimon.",
    43: "Restores a large amount of MP to one Digimon.",
    44: "Restores a great amount of MP to one Digimon.",
    45: "Restores a small amount of MP to one horizontal row of Digimon.",
    46: "Restores a moderate amount of MP to one horizontal row of Digimon.",
    47: "Restores a large amount of MP to one horizontal row of Digimon.",
    48: "Restores a great amount of MP to one horizontal row of Digimon.",
    49: "Removes Health Down and restores half of one Digimon's HP and MP.",
})

_BATCH_4I_ENTRY30 = [
    "A standard glove sold at the Penmon Shop.",
    "A large hammer sold at the Penmon Shop.",
    "A giant hammer sold at the Penmon Shop.",
    "A small needle sold at the Penmon Shop.",
    "A standard needle sold at the Penmon Shop.",
    "A large sword sold at the Penmon Shop.",
    "A giant sword sold at the Penmon Shop.",
    "A weed-covered sword with terrible cutting power.",
    "An East Knuckle City specialty: a red, spiked knuckle.",
    "A West Knuckle City specialty: a blue, spiked knuckle.",
    "A Skull City specialty: a staff tipped with a skull.",
    "A mushroom glove that scatters spores. Makes Paralysis and Poison easier to inflict.",
    "A stun gun that attacks with current. Makes Paralysis easier to inflict.",
    "A soft red glove that increases accuracy.",
    "A gun that riddles enemies with holes and raises critical-hit chance.",
    "A glove that makes Sleep easier to inflict and increases accuracy.",
    "A giant mechanical gun that makes enemies easier to Melody.",
    "A slim, delicate hammer that makes Confusion easier to inflict.",
    "A mechanical gun that makes Paralysis and Curse easier to inflict.",
    "A round, spiked hammer that raises critical-hit chance.",
    "A gun that makes Curse easier to inflict and raises critical-hit chance.",
    "A hammer that improves Melody chance and accuracy.",
    "A bazooka that makes Confusion, Blind, and MP Drain easier to inflict.",
    "A spear that makes Paralysis easier to inflict and increases accuracy.",
    "A beginner's katana that raises critical-hit chance.",
    "A spear that makes Confusion easier to inflict and increases accuracy.",
    "A katana that makes Confusion and Blind easier to inflict.",
    "A freely extendable staff that improves Melody chance.",
    "A katana engraved with cursed writing that makes Curse easier to inflict.",
    "A harpoon for catching underwater prey that raises critical-hit chance.",
    "A sword that makes Confusion easier to inflict and increases MP Drain.",
    "A spear that makes Confusion easier to inflict and increases accuracy.",
    "A sacred ritual dagger wielded by a god. Improves Melody chance.",
    "A staff that raises critical-hit chance and accuracy.",
    "Shuriken worn on both hands and feet. Makes Confusion easier to inflict.",
    "A club made from SkullGreymon's bones. Increases EXP earned in battle.",
    "An axe that improves HP Drain chance and increases the amount drained.",
    "A sturdy steel pestle that increases bits earned in battle.",
    "A sword that increases battle EXP and improves Melody chance.",
    "A hammer that raises critical-hit chance and improves Melody chance.",
    "A shining white sacred sword that increases EXP earned in battle.",
    "A giant sword that cuts enemies in two and improves Melody chance.",
    "A shining two-handed sword that raises critical-hit chance.",
    "A giant morning star that raises critical-hit chance.",
    "A sword that makes Confusion easier to inflict and increases accuracy.",
    "A giant pillar of ice that makes Curse easier to inflict.",
    "A sword that increases bits earned and guarantees successful escape.",
    "An explosively powerful flaming greatsword that improves Melody chance.",
    "A staff that raises critical-hit chance and makes Curse easier to inflict.",
    "A gun that makes Blind easier to inflict and increases accuracy.",
]

_BATCH_4I_ENTRY31 = [
    "A Garurumon-shaped gun that makes Paralysis and Confusion easier to inflict.",
    "An arm-mounted energy cannon that increases accuracy.",
    "Giant claws worn on both arms that raise critical-hit chance.",
    "Claws that improve Poison and Curse chance and increase Poison damage.",
    "A katana that makes Curse easier to inflict and raises critical-hit chance.",
    "A spear that increases Poison damage and EXP earned in battle.",
    "A katana that improves Confusion and Poison chance and raises critical-hit chance.",
    "A giant spear that makes Paralysis, Sleep, Confusion, and Poison easier to inflict.",
    "A katana that makes Curse easier to inflict and raises critical-hit chance.",
    "A greatsword that improves Melody chance and accuracy.",
    "A shining sacred spear that raises critical-hit chance.",
    "A bow that raises critical-hit chance and accuracy.",
    "Berenjena's sister gun. Increases EXP earned in battle.",
    "A dagger that increases both HP Drain and MP Drain.",
    "A sword that increases accuracy and improves Melody chance.",
    "A sword that makes Blind easier to inflict and raises critical-hit chance.",
    "A sacred spear focused with energy. Increases EXP earned in battle.",
    "A staff that improves Confusion and Poison chance and increases bits earned.",
    "A sword that improves Melody chance and increases EXP earned in battle.",
    "A spear that improves Poison chance and damage and raises critical-hit chance.",
    "A sword that improves Melody chance and raises critical-hit chance.",
    "A sword wrapped in blue flame that raises Attack and Defense.",
    "An axe wrapped in dim light that raises Attack and Defense.",
    "Gloves brought back by a great explorer. Increase bits earned in battle.",
    "A sword usable only by Holy Beast Digimon. Grants complete Curse immunity.",
    "A machete usable only by Beast Digimon. Grants immunity to Blind and Shuffle.",
    "A sacred treasure usable only by Angel Digimon. Grants complete Confusion immunity.",
    "A cannon usable only by Demon Digimon. Grants complete Curse immunity.",
    "A spear usable only by Aquatic Digimon. Grants complete Shuffle immunity.",
    "A spear usable only by Machine Digimon. Nullifies enemy Poison.",
    "A sword usable only by Bird Digimon. Grants complete Shuffle immunity.",
    "A spear usable only by Insect Digimon. Nullifies enemy Poison.",
    "A whip usable only by Plant Digimon. Grants complete Paralysis immunity.",
    "A legendary sword passed down in the El Est Zone.",
    "A small helmet sold at the Penmon Shop.",
    "A standard helmet sold at the Penmon Shop.",
    "A sturdy cape sold at the Penmon Shop.",
    "An extremely durable cape sold at the Penmon Shop.",
    "A small vest sold at the Penmon Shop.",
    "A standard vest sold at the Penmon Shop.",
    "A sturdy suit sold at the Penmon Shop.",
    "An extremely durable suit sold at the Penmon Shop.",
    "A rusted, battered shield that looks ready to break.",
    "A Guruguru City specialty: glasses that make you look studious.",
    "A Kumonosu City specialty: underwear that occasionally looks transparent.",
    "A Papyrus City specialty: a T-shirt made from special paper.",
    "A flower-shaped helmet that reduces the chance of Paralysis.",
    "A headband that improves evasion and makes escape more likely to succeed.",
    "A feathered tiara that reduces the chance of Confusion and MP Drain.",
    "A red-cloth scarf that reduces the chance of Paralysis and Blind.",
]

_BATCH_4I_ENTRIES[30] = dict(enumerate(_BATCH_4I_ENTRY30))
_BATCH_4I_ENTRIES[31] = dict(enumerate(_BATCH_4I_ENTRY31))

_BATCH_4I_ENTRY32 = [
    "An umbrella that improves evasion and increases bits earned in battle.",
    "A Western-style red scarf that reduces the chance of Poison.",
    "A pirate-favored hat that reduces the chance of Paralysis and Blind.",
    "An apprentice wizard's cape that reduces the chance of Confusion and Blind.",
    "A topknot helmet that reduces the chance of Sleep.",
    "A red scarf favored by black-and-white beasts. Resists HP Drain and MP Drain.",
    "A small but extremely hard helmet that reduces the chance of Curse.",
    "A cape that improves evasion and reduces the chance of HP Drain and Poison.",
    "A vest often worn by Goblimon that makes escape more likely to succeed.",
    "A small turtle-shell shield that reduces the chance of Sleep.",
    "A suit made from an eggshell that reduces the chance of Paralysis.",
    "A shield made from a giant clam shell that reduces the chance of Confusion.",
    "A powered suit large enough to ride in. Reduces the chance of Paralysis and Poison.",
    "A plate that reduces the chance of Confusion and improves evasion.",
    "Armor made from steel scales that reduces the chance of Paralysis and Blind.",
    "A fox-mask shield that improves evasion.",
    "A monkey-shaped suit that resists Confusion and makes escape more likely.",
    "A shining shield of sacred energy that reduces the chance of Blind and Shuffle.",
    "A suit that reduces the chance of Sleep and improves evasion.",
    "A plate that resists Paralysis and makes escape more likely.",
    "Earrings that resist Shuffle and increase EXP earned in battle.",
    "A mask that resists Shuffle and makes escape more likely.",
    "Sunglasses that grant Shuffle immunity and improve Melody chance.",
    "A festival mask that resists Shuffle and increases EXP earned in battle.",
    "Denim pants that grant Shuffle immunity and improve evasion.",
    "A cute dragon costume that reduces the chance of Shuffle and Curse.",
    "A veil that resists Shuffle and increases bits earned in battle.",
    "An insect-like mask that reduces the chance of Paralysis, Shuffle, and Poison.",
    "A bean-sized but extremely hard helmet that reduces the chance of HP Drain.",
    "A helmet with giant eyes that reduces the chance of Blind and Curse.",
    "A blue cape as light as the wind that improves evasion.",
    "A lavish golden crown that increases bits earned in battle.",
    "A jacket that improves evasion and guarantees successful escape.",
    "A justice scarf that resists Blind and grants complete Curse immunity.",
    "A helmet made in Area 51 that reduces the chance of Paralysis, Confusion, and Blind.",
    "A helmet made from Kuramon data that grants complete Poison immunity.",
    "A robe that resists Blind and Poison and grants complete Confusion immunity.",
    "Armor once worn by an Eastern dragon god that improves evasion.",
    "Armor that grants Paralysis immunity and resists Confusion, HP Drain, and Poison.",
    "A shield that resists Blind and Poison and grants complete Curse immunity.",
    "Armor that resists Blind and Shuffle and improves evasion.",
    "A suit that resists Blind and Poison and improves evasion.",
    "Wings that resist Curse and improve evasion.",
    "A plate that resists Paralysis, Confusion, and Blind and improves evasion.",
    "A shield that resists Curse and improves Melody chance.",
    "Gallantmon's sacred shield. Grants complete Curse immunity.",
    "A scarf that resists Shuffle and increases EXP earned in battle.",
    "A headband that increases bits earned and resists MP Drain and Shuffle.",
    "A festival mask that resists Shuffle and improves evasion.",
    "A mask that resists Shuffle and Poison and improves evasion.",
]

_BATCH_4I_ENTRY33 = [
    "A hairpin that resists Shuffle and increases bits earned in battle.",
    "A mask that improves evasion and grants complete Sleep immunity.",
    "A shield that raises Attack and Defense and resists Shuffle.",
    "A dark chain that sweeps everything aside and resists Shuffle and Poison.",
    "A motorcycle that grants Shuffle immunity and guarantees successful escape.",
    "A ring that draws out sacred power and grants immunity to Health Down and Shuffle.",
    "A bracelet that produces a sword and shield and raises Attack and Defense.",
    "Small earrings made by Calumon that raise Attack and Defense.",
    "A bracelet brought back by a great explorer that raises Attack and Defense.",
    "A shield equippable only by Holy Beast Digimon. Makes Blind easier to inflict.",
    "A jacket equippable only by Beast Digimon. Improves Melody chance.",
    "A shield equippable only by Angel Digimon. Makes Paralysis easier to inflict.",
    "A box equippable only by Demon Digimon. Makes Confusion easier to inflict.",
    "Armor equippable only by Aquatic Digimon. Improves evasion.",
    "A shield equippable only by Machine Digimon. Increases accuracy.",
    "An aura equippable only by Bird Digimon. Makes Curse easier to inflict.",
    "Armor equippable only by Insect Digimon. Makes Poison easier to inflict.",
    "A jewel equippable only by Plant Digimon. Makes HP Drain easier to inflict.",
    "A legendary shield passed down in the El Est Zone.",
    "Slightly raises the trained Digimon's maximum HP.",
    "Moderately raises the trained Digimon's maximum HP.",
    "Greatly raises the trained Digimon's maximum HP.",
    "Slightly raises the trained Digimon's maximum MP.",
    "Moderately raises the trained Digimon's maximum MP.",
    "Greatly raises the trained Digimon's maximum MP.",
    "Slightly raises the trained Digimon's Attack.",
    "Moderately raises the trained Digimon's Attack.",
    "Greatly raises the trained Digimon's Attack.",
    "Slightly raises the trained Digimon's Defense.",
    "Moderately raises the trained Digimon's Defense.",
    "Greatly raises the trained Digimon's Defense.",
    "Slightly raises the trained Digimon's Speed.",
    "Moderately raises the trained Digimon's Speed.",
    "Greatly raises the trained Digimon's Speed.",
    "Slightly raises the trained Digimon's Spirit.",
    "Moderately raises the trained Digimon's Spirit.",
    "Greatly raises the trained Digimon's Spirit.",
    "Slightly raises Farm EXP. Holy Beast Digimon gain a larger bonus.",
]

_BATCH_4I_ENTRIES[32] = dict(enumerate(_BATCH_4I_ENTRY32))
_BATCH_4I_ENTRIES[33] = dict(enumerate(_BATCH_4I_ENTRY33))

assert set(_BATCH_4I_ENTRIES) == set(range(27, 34))
assert set(_BATCH_4I_ENTRIES[27]) == set(range(27, 50))
for _entry_index in range(28, 33):
    assert set(_BATCH_4I_ENTRIES[_entry_index]) == set(range(50))
assert set(_BATCH_4I_ENTRIES[33]) == set(range(38))
for _entry_index, _strings in _BATCH_4I_ENTRIES.items():
    for _string_index, _localized_text in _strings.items():
        OVERRIDES[(4, _entry_index, _string_index)] = _localized_text

# Batch 4J: MESPAK04 entry 33 through the opening of entry 41.
_BATCH_4J_ENTRIES = {33: {}, 34: {}}

_BATCH_4J_FARM_BONUSES = [
    (33, 38, "Moderately", "Holy Beast"),
    (33, 39, "Greatly", "Holy Beast"),
    (33, 40, "Slightly", "Beast"),
    (33, 41, "Moderately", "Beast"),
    (33, 42, "Greatly", "Beast"),
    (33, 43, "Slightly", "Angel"),
    (33, 44, "Moderately", "Angel"),
    (33, 45, "Greatly", "Angel"),
    (33, 46, "Slightly", "Demon"),
    (33, 47, "Moderately", "Demon"),
    (33, 48, "Greatly", "Demon"),
    (33, 49, "Slightly", "Machine"),
    (34, 0, "Moderately", "Machine"),
    (34, 1, "Greatly", "Machine"),
    (34, 2, "Slightly", "Aquatic"),
    (34, 3, "Moderately", "Aquatic"),
    (34, 4, "Greatly", "Aquatic"),
    (34, 5, "Slightly", "Bird"),
    (34, 6, "Moderately", "Bird"),
    (34, 7, "Greatly", "Bird"),
    (34, 8, "Slightly", "Insect"),
    (34, 9, "Moderately", "Insect"),
    (34, 10, "Greatly", "Insect"),
    (34, 11, "Slightly", "Plant"),
    (34, 12, "Moderately", "Plant"),
    (34, 13, "Greatly", "Plant"),
]
for _entry_index, _string_index, _amount, _family in _BATCH_4J_FARM_BONUSES:
    _BATCH_4J_ENTRIES[_entry_index][_string_index] = (
        f"{_amount} raises Farm EXP. {_family} Digimon gain a larger bonus."
    )

for _offset, _quality in enumerate(
    ("standard", "decent", "good", "excellent", "exceptional"), 14
):
    _BATCH_4J_ENTRIES[34][_offset] = (
        f"Assign this Farm job to have a Digimon craft a {_quality} weapon."
    )
for _offset, _quality in enumerate(
    ("standard", "decent", "good", "excellent", "exceptional"), 19
):
    _BATCH_4J_ENTRIES[34][_offset] = (
        f"Assign this Farm job to have a Digimon craft {_quality} armor."
    )
_BATCH_4J_ENTRIES[34].update({
    24: "Friendship Up 1. No item.",
    25: "Friendship Up 2. No item.",
    26: "Find 100 bits. No item.",
    27: "Find 500 bits. No item.",
    28: "Find 1,000 bits. No item.",
})

_BATCH_4J_DIGISCORE_NAMES = {
    34: [
        "Kuramon (Down)", "Kuramon (Up)", "IceDevimon", "Aquilamon", "Agunimon",
        "Ankylomon", "Airdramon", "ExVeemon", "Angemon", "Kabuterimon (Down)",
        "Kabuterimon (Up)", "Gaogamon", "Gargomon", "Garurumon", "Kyubimon",
        "Chrysalimon", "Growlmon", "Greymon L", "Gekomon", "Seasarmon", "Coelamon",
    ],
    35: [
        "Shellmon", "Stingmon", "Tankmon", "Tyrannomon", "Gatomon", "Devimon",
        "Dorugamon", "Apemon", "Bakemon", "Firamon", "Buraimon", "Minotarumon",
        "Musyamon", "Reptiledramon", "Dolphmon", "Leomon (Down)", "Leomon (Up)",
        "Lekismon", "Argomon Ultimate", "Meteormon", "Infermon", "Vajramon",
        "Myotismon", "Angewomon", "Kabukimon", "Karatenmon", "Kimeramon",
        "Kyukimon", "Gigadramon", "Crescemon", "GrapLeomon", "Grademon",
        "Cerberumon", "Shakkoumon", "Silphymon", "Sinduramon", "Cherrymon",
        "SkullBaluchimon", "Taomon", "Tyilinmon", "Dinobeemon", "DoruGreymon",
        "Bastemon", "Paildramon", "Pandamon", "Phantomon", "Flaremon", "Butenmon",
        "Blossomon", "Whamon",
    ],
    36: [
        "Mermaimon", "Magnamon", "MachGaogamon", "MarineDevimon", "MegaSeadramon",
        "Megadramon", "WarGrowlmon", "Monzaemon", "Yatagaramon", "RiseGreymon",
        "Rapidmon", "Lillymon", "RookChessmon", "Lucemon FM", "LadyDevimon",
        "WereGarurumon", "Wisemon", "AeroVeedramon", "MagnaAngemon",
        "MetalGreymon L", "Anubismon", "Apollomon", "Alphamon", "WarGreymon",
        "Vikemon", "Valkyrimon", "Examon", "Ophanimon", "Gaiomon", "Cannondramon",
        "GigaSeadramon", "Craniamon", "Eaglemon", "Chronomon Holy Mode",
        "GranDracmon", "Cherubimon Good", "Goldramon", "SaberLeomon", "Sakuyamon",
        "Zanbamon", "Justimon", "JumboGamemon", "SkullMammothmon", "Sleipmon",
        "Seraphimon", "MegaGargomon", "Darkdramon", "Daipenmon", "Dianamon",
        "Diaboromon",
    ],
    37: [
        "Creepymon", "Devitamamon", "Gallantmon (Down)", "Gallantmon (Up)",
        "Duftmon", "Dorugoramon", "Neptunemon", "HiAndromon", "Piedmon (Down)",
        "Piedmon (Up)", "Puppetmon", "Pharaohmon", "PrinceMamemon", "Beelzemon",
        "Phoenixmon", "Magnadramon", "Boltmon", "Minervamon", "Millenniummon",
        "Machinedramon (Down)", "Machinedramon (Up)", "Megidramon", "MetalEtemon",
        "MetalGarurumon", "Mercurimon", "Lilithmon", "Ravemon", "Rosemon",
        "Lotosmon", "AncientIrismon", "AncientGarurumon", "AncientGreymon",
        "AncientSphinxmon", "AncientTroiamon", "AncientBeetmon",
        "AncientVolcanomon (Down)", "AncientVolcanomon (Up)", "AncientMermaimon",
        "AncientMegatheriummon", "AncientWisemon", "BAN Leomon", "GranKuwagamon",
        "HerculesKabuterimon", "Imperialdramon DM", "MagnaAngemon",
        "MetalSeadramon", "MirageGaogamon", "ShineGreymon", "TigerVespamon",
        "UlforceVeedramon",
    ],
    38: [
        "VenomMyotismon", "Armageddemon", "Apocalymon", "Aegisdramon",
        "Varodurumon", "Omnimon", "Chaosdramon", "Chaosmon", "Ebonwumon",
        "Zhuqiaomon", "Susanoomon (Down)", "Susanoomon (Up)", "Azulongmon",
        "Gallantmon Crimson Mode", "Baihumon", "Ravemon Burst Mode",
        "Rosemon Burst Mode", "MaloMyotismon", "ChaosGallantmon",
        "Imperialdramon FM", "Imperialdramon PM", "MirageGaogamon Burst Mode",
        "MoonMillenniummon", "ShineGreymon Burst Mode", "ShineGreymon Ruin Mode",
        "ZeedMillenniummon", "Greymon", "Shoutmon (Down)", "Shoutmon (Up)",
        "Shoutmon X2", "Shoutmon X3", "Shoutmon X4", "Shoutmon X5",
        "Shoutmon X4B", "Jet Sparrow", "SkullKnightmon", "Star Sword",
        "DarkKnightmon", "Dorulu Cannon", "Beelzemon (Down)", "Beelzemon (Up)",
        "MetalGreymon", "GreyKnightsmon", "Shoutmon X3GM", "Shoutmon X3SD",
        "Shoutmon X4S", "Shoutmon X5S", "Spadamon",
    ],
}
for _entry_index, _names in _BATCH_4J_DIGISCORE_NAMES.items():
    _start_index = 29 if _entry_index == 34 else 0
    _BATCH_4J_ENTRIES.setdefault(_entry_index, {})
    for _offset, _digimon_name in enumerate(_names, _start_index):
        _BATCH_4J_ENTRIES[_entry_index][_offset] = (
            f"{_digimon_name} DigiScore. Description text."
        )

_BATCH_4J_ENTRIES[38].update({
    48: "A portable tent for resting. Usable wherever there is a Tent Point.",
    49: "A passport from Biyomon. Carry it to use the Digimon Air Corps.",
})

_BATCH_4J_ENTRIES[39] = {
    0: "The El Est Zone Code Crown. Proof of the legendary Weapon Digimon's master.",
    13: "Sunblock from Wendimon. It can give even the palest Digimon a deep tan.",
    14: "A gift from one of Terilop's biggest fans, beautifully wrapped with a ribbon.",
    15: "An autograph board from Terilop with a very clumsy drawing.",
    16: "A phone strap from Terilop with two Terilop dolls holding hands.",
    17: "A Numemon photo showing a tiny flower balanced on its tongue.",
    18: "A Sukamon postcard showing it crossing both arms in a signature pose.",
    19: "A candid Numemon-and-Sukamon photo that any NumeSuka fan would treasure.",
    20: "An autograph board from NumeSuka with an impressively bad smell.",
    21: "A hair tie from Angewomon with a red strawberry charm.",
    22: "A hair tie from Angewomon with a plain marimo charm.",
    23: "Treasure recovered from the eastern pirates: a bar of pure silver.",
    24: "Treasure recovered from the southern pirates: a pearl almost as large as Koromon.",
    25: "Treasure recovered from the western pirates: a glowing blue heart-shaped sapphire.",
    26: "Treasure recovered from the northern pirates: a large golden crown.",
    27: "A special razor from Zudomon that can shave even the toughest hair cleanly.",
    28: "A miracle razor from Drimogemon that can shave even the toughest hair cleanly.",
    29: "A thick book from Wisemon, packed with writing in an unknown script.",
    30: "A large feather from Diatrymon. It is handy for dusting.",
    31: "Bits forced on you by Devimon. They look extremely suspicious.",
    32: "Bits forced on you by Vilemon. They look extremely suspicious.",
    33: "A fist-sized, fishy-smelling meteorite that glows an ominous black.",
    34: "A head-sized, dubious meteorite that glows an ominous black.",
    35: "A bean-sized, gunpowder-smelling meteorite that glows an ominous black.",
    36: "A bean-sized, very fine meteorite with an appraisal certificate from Vademon.",
    37: "A voice recorder for recording an interview with an admired Digimon.",
    38: "Dinobeemon voice data containing a recorded interview.",
    39: "Paildramon voice data containing a recorded interview.",
    40: "LadyDevimon's lost planner, filled with the idols' schedules.",
    41: "A signed CD from Terilop with slightly pretentious handwriting.",
    42: "A giant bronze statue received as thanks for rescuing Terilop.",
    43: "An autograph board from Terilop with writing that looks like a cute drawing.",
    44: "A crown like a blazing flame. Carrying it is said to bring good luck.",
    45: "A crown like falling snow. Carrying it is said to bring good luck.",
    46: "A crown like pouring light. Carrying it is said to bring good luck.",
    47: "A crown like rising darkness. Carrying it is said to bring good luck.",
    48: "A sharpened bone from a skeletal Digimon, polished to a keen shine.",
    49: "Everyone's favorite legendary food. The Penmon Shop does not sell it.",
}
for _index in range(1, 13):
    _BATCH_4J_ENTRIES[39][_index] = f"Call Slot {_index + 2:03d}. Description text."

_BATCH_4J_ENTRIES[40] = {
    0: "Memory recovered from Devimon containing Terriermon's precious data.",
    1: "A DigiNoir for Leomon. It is delicious and restores energy when eaten.",
    2: "A score entrusted by the stone-monument Digimon. Its purpose is unknown.",
    3: "Unknown data left by Kuramon. It resembles someone's score.",
    4: "A passion flower from Rosemon, often given during a marriage proposal.",
    5: "A seductive flower from Lotosmon. Giving it to someone can leave them lovestruck.",
    9: "Proof that you defeated the powerful Aegisdramon as a kindhearted gentleman.",
    10: "Proof that you defeated the powerful Apocalymon as a courageous hero.",
    11: "Proof that you conquered the ultimate Coliseum as a legendary champion.",
}
for _index, _slot in zip(range(6, 9), range(343, 346)):
    _BATCH_4J_ENTRIES[40][_index] = f"Call Slot {_slot}. Description text."
for _index, _slot in zip(range(12, 23), range(349, 360)):
    _BATCH_4J_ENTRIES[40][_index] = f"Call Slot {_slot}. Description text."

_BATCH_4J_MAP_NAMES = [
    "Sky Fort", "Fort Yard", "West Knuckle Coast", "East Knuckle Coast",
    "West Guruguru Amazon", "East Guruguru Amazon", "East Digital Space",
    "West Skull Glacier", "East Skull Glacier", "West Kumonosu Ruins",
    "East Kumonosu Ruins", "North Papyrus Desert", "South Papyrus Desert",
    "Flower Grasslands", "Darkness Tunnel", "Tokona Sea", "Tokona Coast",
    "West Crystal Volcano", "East Crystal Volcano", "Crystal Mine",
    "Crystal Cave", "North Stealth Valley", "South Stealth Valley",
    "North Lost Space", "South Lost Space", "North Digital Space",
    "South Digital Space",
]
for _index, _area_name in enumerate(_BATCH_4J_MAP_NAMES, 23):
    _BATCH_4J_ENTRIES[40][_index] = f"A map that displays the {_area_name} area."

_BATCH_4J_ENTRIES[41] = {
    0: "Call Slot 527. Description text.",
    1: "Call Slot 528. Description text.",
    2: "Call Slot 529. Description text.",
    3: "A key that opens the Sky Port gate in Sky Fort.",
    4: "A key that opens the East Knuckle City Port gate on East Knuckle Coast.",
    5: "A key that opens the Guruguru West Port gate in West Guruguru Amazon.",
    6: "A key that opens the Guruguru City Port gate in East Guruguru Amazon.",
    7: "A key that opens the Skull City Port gate in West Skull Glacier.",
    8: "A key that opens the Skull East Port gate in East Skull Glacier.",
    9: "A key that opens the Kumonosu West Port gate in West Kumonosu Ruins.",
    10: "A key that opens the Kumonosu City Port gate in East Kumonosu Ruins.",
    11: "A key that opens the Papyrus North Port gate in North Papyrus Desert.",
    12: "A key that opens the Papyrus City Port gate in South Papyrus Desert.",
    13: "A key that opens the Flower Port gate in Flower Grasslands.",
    14: "A key that opens the Tokona Port gate on Tokona Coast.",
    15: "A key that opens the Earth Port gate at Earth Fort in East Crystal Volcano.",
    16: "A key that opens the Crystal Mine Port gate in Crystal Mine.",
    17: "A key that opens the Stealth North Port gate in North Stealth Valley.",
    18: "A key that opens the Lost North Port gate in North Lost Space.",
    19: "A key that opens the Lost South Port gate in South Lost Space.",
    20: "A key that opens the Digital North Port gate in North Digital Space.",
    21: "Call Slot. Description text.",
    22: "Call Slot 569. Description text.",
    23: "Call Slot 570. Description text.",
    24: "A key that opens the gate in West Guruguru Amazon 4.",
    25: "A key that opens the gate in East Guruguru Amazon 2.",
    26: "A key that opens the gate in West Kumonosu Ruins 1.",
    27: "A key that opens the gate in East Kumonosu Ruins 3.",
    28: "A key that opens the gate in East Knuckle Coast 3.",
    29: "Give this to the Service Counter to receive a gift from Koromon.",
    30: "Give this to the Service Counter to receive a gift from Guilmon.",
    31: "Give this to the Service Counter to receive a gift from Palmon.",
    32: "Give this to the Service Counter to receive a gift from Gomamon.",
    33: "Give this to the Service Counter to receive a gift from DemiDevimon.",
    34: "Give this to the Service Counter to receive a gift from Lopmon.",
}

assert set(_BATCH_4J_ENTRIES) == set(range(33, 42))
assert set(_BATCH_4J_ENTRIES[33]) == set(range(38, 50))
for _entry_index in range(34, 41):
    assert set(_BATCH_4J_ENTRIES[_entry_index]) == set(range(50))
assert set(_BATCH_4J_ENTRIES[41]) == set(range(35))
for _entry_index, _strings in _BATCH_4J_ENTRIES.items():
    for _string_index, _localized_text in _strings.items():
        OVERRIDES[(4, _entry_index, _string_index)] = _localized_text

# Batch 4K: final MESPAK04 service tickets and the opening MESPAK05 Farm dialogue.
_BATCH_4K_TICKET_NAMES = {
    41: [
        "Goblimon", "Lucemon", "Dracomon", "Phascomon", "Devimon", "Numemon",
        "Kabuterimon", "Bakemon", "Togemon", "Guardromon", "ExVeemon", "Stingmon",
        "Chrysalimon", "DarkTyrannomon", "Ikkakumon",
    ],
    42: [
        "Frigimon", "Dolphmon", "Agunimon", "MetalGreymon L", "SkullGreymon",
        "Angewomon", "Tylomon", "LadyDevimon", "Garudamon", "MegaKabuterimon Red",
        "Taomon", "Parrotmon", "Pandamon", "Sinduramon", "Whamon", "Tyilinmon",
        "Cherrymon", "ExTyrannomon", "Flamedramon", "Bastemon", "Cerberumon",
        "BlueMeramon", "Scorpiomon", "Nefertimon", "Caturamon", "Gallantmon",
        "BAN Leomon", "Goldramon", "Valkyrimon", "Pharaohmon", "Spinomon",
        "AncientVolcanomon", "Daipenmon", "PlatinumNumemon", "Dinorexmon",
        "Chaosdramon", "Ogudomon", "Monitamon", "DonDokoMon", "Bommon",
        "Shoutmon B", "Greymon O", "SkullKnightmon BR", "MadLeomon", "Tactimon",
        "Blastmon", "Gaossmon", "Troopmon", "Chikurimon", "Chibickmon",
    ],
}
for _entry_index, _names in _BATCH_4K_TICKET_NAMES.items():
    _start_index = 35 if _entry_index == 41 else 0
    for _string_index, _digimon_name in enumerate(_names, _start_index):
        OVERRIDES[(4, _entry_index, _string_index)] = (
            f"Give this to the Service Counter to receive a gift from {_digimon_name}."
        )
OVERRIDES[(4, 43, 0)] = "Call Slot. Description text."

_BATCH_4K_ENTRY0 = [
    "Huh? Is this a scale? Guess I'll see what I weigh.",
    "Not too light, not too heavy. Looks like my max HP went up a little, too!",
    "Whoa... No way that number's right. Maybe I should pretend I never saw it...",
    "Huh? A belt machine? Exercise gadgets aren't really my style, but...",
    "Whew... This thing's actually a decent workout! Looks like my max HP went up a fair bit.",
    "Forget exercise--this thing shakes way too much!",
    "Hey, a treadmill! I could just run outside... but I've always wanted to try one!",
    "Now that I'm on it, this feels pretty good! My max HP went way up, too!",
    "Running without going anywhere feels kinda pointless...",
    "Huh? A crystal ball? It's pretty, but what do you even do with it?",
    "My max MP went up a little. And I hate to admit it, but I saw a flash... Was that my future?!",
    "I thought I saw something... Nope. Just my face reflected upside down!",
    "What's this? Tarot cards?",
    "Whoaaa! My max MP went up?! Is this what they call the power of magic?!",
    "Magic's just dumb superstition--whoa! Why does my stomach suddenly hurt? Is this magical payback?!",
    "Oh, it's a pyramid. Think I'll rest inside for a while...",
    "Man, I feel refreshed! My max MP went up, too. Is this pyramid power?!",
    "I suddenly feel completely drained... Is this negative pyramid power?!",
    "Hey, a punching bag! Time to give it a few shots!",
    "Heh! How's that? My Attack shot up, and I'm feeling great!",
    "Heh! How's that? ...I said, right before twisting my wrist. This is the worst!",
    "Uh... a training log? I'm supposed to toughen up by ramming into this thing?",
    "How's that?! My Attack went way up!",
    "Does doing something this boring really make me stronger...?",
    "Found a giant boulder! I'm supposed to push this, right?",
    "Whoa, my Attack went way up! That was a lot easier than I expected.",
    "It isn't budging at all. Does this thing really move?",
    "Oh, sweet--a punching machine! I'm gonna hit this thing with everything I've got!",
    "Heh! Not bad, right? Looks like my Defense went up!",
    "Th-that's enough! I'll let you off easy this time!",
    "Whoa! Is this a training cannon? I'm supposed to catch the shot? All right--fire!",
    "Okay, I took it! Defense up! Still doesn't feel worth the pain, though...",
    "I said fire, but not like that, idiot! Nobody could just stand there and take this!",
    "Hey, what's with this iron ball? Catching it counts as training?",
    "I caught it through sheer guts! My Defense went up, and now I'm braver, too!",
    "Who can do this?! Bring me the genius who invented it! This isn't training--it's torture!",
    "Well, well... a bookshelf! Guess I could try reading once in a while.",
    "Heh-heh! Reading made me smarter!",
    "Heh-heh! I read it... and understood absolutely nothing!",
    "Why is there a study desk here? Does studying really count as training?",
    "Forced myself to study and forced my Spirit up! Any more and my head might explode!",
    "Studying isn't training. This is torture!",
    "I know this one! It's a magic circle! Time to score some serious magical power!",
    "Whoa! My head feels unbelievably clear! Did my Spirit really just go up?!",
    "Nothing happened. Yeah... I still don't believe in magic.",
    "You want me to do side-to-side jumps? Fine. Let's do this!",
    "This is a piece of cake! And my Speed went up!",
    "All that work for nothing. There goes my motivation...",
    "Whoa, a trampoline! Honestly, I love bouncing around on these things...",
    "Boing, boing, trampoline! Trampoline, boing! Speed up--boing, boing, boing!",
    "Boing, boing, trampoline! Wait--that last boing was my Achilles tendon!",
    "Whoa, a running wheel! I'm supposed to run inside this thing?",
    "High-speed running! My Speed went way up!",
    "It's cramped, it spins, and I'm getting dizzy! Who can do this?!",
    "Hmm, is this a Digimon keychain game? Looks fun. I'll give it a try!",
    "Wow, that was so much fun I lost track of time! Our Friendship went up a little!",
    "It was fun, but pretty hard. That's a little frustrating...",
    "Hmm, this is a cell phone. I'll send Taiki a message!",
    "Yay! Taiki wrote back! Our Friendship went up a fair bit!",
    "Hmm... No reply from Taiki. That's disappointing...",
    "Hmm, Taiki left his digital camera here. Maybe I'll take a picture of myself!",
    "Perfect! I hope Taiki sees it. Our Friendship went way up!",
    "Aww, I didn't make it in time. That's too bad...",
    "Whoa, a ring of fire! Looks fun. I'm gonna try it!",
    "Yahoo! Thrilling and exciting! My EXP went up, too!",
    "Hwaaah! That's hot! Who can do this?! My butt's gonna burn!",
    "A Fire Road? That looks hot... I'm supposed to cross this? Who thought this up?",
    "My body and soul are on fire! And my EXP went up!",
    "Yaaah! Who can do this?! Whoever invented it should try it themselves!",
    "Fireworks? Huh... That actually sounds kind of fun.",
    "Whoa, amazing! They're gorgeous! My EXP went up, too--huge success!",
    "These fireworks won't pop, fly, glow, launch, or even light...",
    "Whoa, a giant ball! I'm supposed to stand on it?",
    "I get EXP for this? Piece of cake!",
    "It looks easy, but this is actually pretty rough...",
    "You want me to walk this tightrope? Interesting. Let's do it!",
    "Huh, that was surprisingly easy and fun! Plus, my EXP went up--two wins at once!",
    "Scary, exhausting, difficult, and falling hurts. This is the worst!",
    "I-is that a circus tent?! What am I supposed to do in there?!",
    "A circus performance raised my EXP instantly! The details are a trade secret!",
    "All that spinning and bending is impossible! Even if I learned it, what good is it to a Digimon?!",
    "Found a mini shower... Do I really have to use this?",
    "That feels amazing! Been a while since I had a shower. My EXP went up, too!",
    "I hate showers. They just get you soaked. It's not like I'll die without one...",
    "Hey, a mini fishing pond! Wonder if I can catch anything.",
    "Whoa, amazing! They're biting like crazy! Fish everywhere, and EXP everywhere!",
    "Not even a nibble. Are there actually fish in here?",
    "I'm supposed to train by standing under this waterfall?",
    "Forget about EXP and quietly endure the waterfall! Which, in the end... raises EXP!",
    "No, no, no! This hurts like crazy, I can't breathe, and it's freezing! What's the point?!",
    "What a beautiful flower. Smells nice, too.",
    "The sweet scent, the beautiful sight... I feel calm, and my EXP went up.",
    "Aah... achoo! H-hachoo! What is this, pollen?!",
    "Huh, a treehouse. Looks pretty nice. Maybe I'll go inside.",
    "This relaxed atmosphere is great... Looks like my EXP went way up.",
    "...No, this isn't for me. Only a forest fairy could live in a place like this.",
    "Hey, a computer! Time to hop on the internet!",
    "Casually scored some rare info! And casually raised my EXP!",
    "...Between us, I've been pretending this whole time. What's the internet?",
    "Hmm... a solar panel. What do I do to make this thing do whatever it does?",
]
assert len(_BATCH_4K_ENTRY0) == 100
for _string_index, _localized_text in enumerate(_BATCH_4K_ENTRY0):
    OVERRIDES[(5, 0, _string_index)] = _localized_text

_BATCH_4K_ENTRY1 = [
    "Whoaaa! What is this thing?! My EXP is shooting up like crazy!",
    "Hwaaah! It shocks! Stop it--turn it off! I'm getting zapped!",
    "A pinball machine, huh? Think I'll play for a while.",
    "Yes! Perfect score! And my EXP went way up with a ping!",
    "I can't get anything right. Is this game even fun?",
    "A little birdhouse. Wonder if any birds are inside...",
    "The little birds are so cute! I feel better, and my EXP went up a little!",
    "No birds, it stinks, it's cramped, and now I'm covered in dust and webs. Total failure!",
    "You want me to try the running high jump? Heh... Fine. Let's do this!",
    "All right! Cleared the bar perfectly, and my EXP went up!",
    "Who cares if I can clear it? Digimon don't need the high jump! Yeah, I'm a sore loser!",
    "That's a diving platform, right? I'm supposed to jump from here...?",
    "I did it! Success! My EXP went up, too!",
    "Who can do this?! It's terrifying!",
    "Is this a phonograph? What am I supposed to do with it?",
    "Whoa, that surprised me. It sounds pretty good! I feel relaxed, and my EXP went up.",
    "Is this thing broken? It won't make a sound...",
    "Hey, I know this--it's a Holy Bell! Think I'll ring it.",
    "What a great sound. Feels like it's cleansing my heart. Not that my heart wasn't already pure! My EXP went up, too.",
    "It won't ring at all. Is it broken, or can only someone with a pure heart ring it...?",
    "This is Stonehenge, right? Am I supposed to walk through it?",
    "Whoaaa! What is this?! Power's surging through me, and my EXP went up!",
    "Nothing happened. Guess it only looks impressive.",
    "What's this? Some weird jar...",
    "Ugh... This is dark medicine! My EXP went up, but it smells awful...",
    "Whoa, that reeks! Looks dangerous. Time to evacuate.",
    "Is this... a cursed box?! I'm curious. Maybe I'll check it out...",
    "Whoa... Is this dark power?! My EXP went up, but I really don't like this feeling!",
    "This thing reeks of bad vibes and traps. Probably better not to touch it...",
    "Is that a Dark Tower?! Why is it here...?",
    "Ugh... What is this power? So this is darkness... My EXP went up, but I feel unsettled.",
    "Nothing happened. Somehow I feel both disappointed and relieved...",
    "Hmm... There's a really pleasant smell coming from around here.",
    "I know! That's Taiki's scent! I hope we can play next time he visits. Our Friendship went up a little!",
    "Hehe, I'm really happy today. We can all live peacefully thanks to Taiki. I wish I could thank him somehow.",
    "Taiki... thank you for everything. We're all truly grateful. I hope those words reached you! Our Friendship went way up!",
    "Huh? What's this...?",
    "It's 100 bits! I'll send them to Taiki right away. He'll be happy!",
    "Huh? What's this...?",
    "Whoa, 500 bits! I'll send them to Taiki. He'll put them to good use!",
    "Huh? What's this...?",
    "Whoa, amazing--1,000 bits! I'll send them to Taiki. We can trust him with them!",
    "Huh? A wild strawberry...",
    "Whoa, this is delicious! Such a great strawberry that my EXP went up!",
    "This strawberry isn't very good. It's not sweet at all, and now I'm bummed...",
    "This branch is practically asking me to climb the tree...",
    "Yes! Made it up the tree! Climbed high, and my EXP went up!",
    "The moment I got up here, my mood dropped. So I climbed a tree... now what?",
]
assert len(_BATCH_4K_ENTRY1) == 48
for _string_index, _localized_text in enumerate(_BATCH_4K_ENTRY1):
    OVERRIDES[(5, 1, _string_index)] = _localized_text

_BATCH_4L_ENTRY1 = {
    48: "Huh? Is this a tree stump? What am I supposed to do with it?",
    49: "Nothing special, but it's not bad training. Looks like my EXP went up a fair bit.",
    50: "Even if I keep ramming this thing... does it really count as training?",
    51: "Whoa, is that tasty sap? They call it tasty, but what does it taste like?",
    52: "Whoa, it really is sweet and delicious! My EXP went way up, too!",
    53: "Ugh, that's unbelievably awful! What part of this is supposed to be tasty?!",
    54: "Maximum HP increased! ^6 -> ^7",
    55: "Maximum MP increased! ^6 -> ^7",
    56: "Attack increased! ^6 -> ^7",
    57: "Defense increased! ^6 -> ^7",
    58: "Speed increased! ^6 -> ^7",
    59: "Friendship increased! ^6 -> ^7",
    60: "Spirit increased! ^6 -> ^7",
    61: "Hmm, that's a scale. Okay, I'll weigh myself!",
    62: "That's just right--perfect! Looks like my max HP went up a little, too!",
    63: "Whoa, I weigh too much... Wh-what a shock!",
    64: "That's a belt machine. Looks like I can exercise while lying down!",
    65: "Whew, that was a really good workout. My max HP went up a fair bit!",
    66: "I-I can't stop shaking. Wh-what do I do...?",
    67: "Oh, a treadmill. Hmm... Maybe I should exercise once in a while.",
    68: "Hehe, this is actually pretty nice! I feel refreshed, and my max HP went up!",
    69: "No more! I'm exhausted. I can't move!",
    70: "Huh? What's this--a crystal ball? It's clear inside and really pretty.",
    71: "Whoa, that startled me! I saw something! My max MP went up a little, too!",
    72: "Nothing's happening. That's kind of boring.",
    73: "Oh, something's here. What is it? I know--tarot cards!",
    74: "Whoa, magical power is flowing into me! My max MP went up a fair bit!",
    75: "Hmm? Nothing happened. Boring...",
    76: "Oh, a pyramid! Perfect. I'll rest inside for a little while.",
    77: "That mysterious power left me refreshed! My max MP went way up somehow!",
    78: "I got lost inside. I can't walk anymore...",
    79: "Hmm, a punching bag? Then I'll practice attacking!",
    80: "I feel stronger again! My Attack went up a little!",
    81: "Ow, that hurts! I'm done for today!",
    82: "A training log, right? Okay... I'm supposed to ram into it!",
    83: "How was that? Pretty good, right? My Attack went up a fair bit!",
    84: "I'm getting tired. That's enough for today!",
    85: "Oh, a giant boulder! I'm supposed to push it and move it, right?",
    86: "That was nothing! Looks like my Attack went way up!",
    87: "It won't move at all. Maybe this was impossible from the start?",
    88: "Looks like this is a punching machine.",
    89: "This is nothing! Looks like my Defense went up a little!",
    90: "W-wait! Stop! I give up!",
    91: "Oh, a training cannon. Okay, I guess I'll train!",
    92: "I held out until the end! Looks like my Defense went up a fair bit!",
    93: "I-it hurts! I hate this training!",
    94: "Hmm, that's an iron ball, right? I get it--I'm supposed to catch it!",
    95: "That was no big deal! Looks like my Defense went way up!",
    96: "N-no way! That's absolutely impossible!",
    97: "Hmm, a bookshelf. I hope it has something fun to read!",
    98: "Haha, there are plenty of fun books! Looks like my Spirit went up a little!",
    99: "Aw, they're all difficult books. What a letdown!",
}
assert set(_BATCH_4L_ENTRY1) == set(range(48, 100))
for _string_index, _localized_text in _BATCH_4L_ENTRY1.items():
    OVERRIDES[(5, 1, _string_index)] = _localized_text

_BATCH_4L_ENTRY2 = {
    0: "Hmm, is that a study desk? I hate studying, but maybe I'll do some for once!",
    1: "Hehe, I got a lot done this time! Looks like my Spirit went up a fair bit!",
    2: "Nope, I can't do it. I'm getting sleepy...",
    3: "Hmm? I know that--it's a magic circle! I wonder what kind of spell it uses.",
    4: "My mind feels incredibly sharp! Maybe I just got way smarter!",
    5: "Huh? Nothing happened. Guess it failed...",
    6: "These are side-to-side jumps, right? I'll give them a try!",
    7: "This is super easy! Looks like my Speed went up a little!",
    8: "Huff, huff... I'm tired. I'm done!",
    9: "Hmm, a trampoline? It looks fun, so I'll try it!",
    10: "Bouncing around was so much fun! Looks like my Speed went up a fair bit!",
    11: "My head's spinning... Ugh, I feel awful.",
    12: "Hmm, that's a running wheel, right? I think you're supposed to run inside it.",
    13: "That felt like a great workout! Looks like my Speed went way up!",
    14: "Huff, huff... No more. I'm so exhausted I might collapse.",
    15: "Oh, a Digimon keychain game. I-is it fun? I'll try it...",
    16: "Th-this is way more fun than I expected! Our Friendship went up a little.",
    17: "I-it's fun, but it might be a little difficult...",
    18: "Oh, a cell phone. Th-then I'll send Taiki a message...",
    19: "He replied! I-I'm so happy! Our Friendship went up a lot!",
    20: "N-no reply... That's disappointing...",
    21: "Taiki must've left this digital camera. M-maybe I'll take a picture of myself...",
    22: "I-I got a good picture! What a relief. Our Friendship went way up!",
    23: "I-I don't really understand how to use it...",
    24: "Hmm, is that a ring of fire? It looks fun. I'll try it!",
    25: "Yay! I burned bright and my EXP burned upward, too!",
    26: "H-hot! I hate this!",
    27: "A Fire Road! It looks really hot... I wonder if I can cross it.",
    28: "I did it! A little courage earned me a little EXP!",
    29: "Whoa, that's way too hot! I'm done!",
    30: "Oh, fireworks! They look fun, so I'll launch them!",
    31: "Wow, they're beautiful! Huge success, and my EXP went way up!",
    32: "Hmm? They won't launch. Did it fail?",
    33: "Wow, what a huge ball! I hope I can stand on it and roll!",
    34: "Yes! That went pretty well! Looks like my EXP went up a little!",
    35: "I can't balance on it! I'm done!",
    36: "Could this be a tightrope? I've always wanted to try one!",
    37: "That went great! It was easy, and my EXP went up a fair bit!",
    38: "That was scary! I'm never doing it again!",
    39: "Oh, a circus tent! Maybe someone can teach me a trick!",
    40: "I learned the trapeze! I'm so happy, and my EXP went way up!",
    41: "No way! I could never do that!",
    42: "Hmm, a mini shower? It looks refreshing. Maybe I'll take one!",
    43: "Wow, it's cold and feels amazing! My EXP went up a little, too!",
    44: "Whoa, this is too cold. Now I feel awful...",
    45: "Let's see... a mini fishing pond? Looks fun. I'll try it!",
    46: "Yay, fish are easy to catch here! My EXP went up a fair bit!",
    47: "Hmm? The fish aren't biting. This isn't fun at all!",
    48: "Hmm, there's a huge waterfall here. Okay, maybe I'll train under it!",
    49: "Yay! Focus under the waterfall! Looks like my EXP went way up!",
    50: "No, it's too cold! Training's over!",
    51: "Hmm, something smells wonderful. Oh, it's coming from this flower!",
    52: "The sweet scent feels so nice! Looks like my EXP went up a little!",
    53: "Aah! A caterpillar! I hate caterpillars!",
    54: "A treehouse! It feels so nice. I'll try living here!",
    55: "I can relax here forever. It's great, and my EXP went way up!",
    56: "No, this won't work. There's no food anywhere!",
    57: "Hmm, is that a computer? Maybe I can use the internet...",
    58: "Yay, it worked! I learned something, and my EXP went up a little!",
    59: "Hmm? How do you even turn on a computer?",
    60: "That's a solar panel. I'm curious how it works...",
    61: "Whoa, electricity is flowing through me! My EXP went up a fair bit!",
    62: "I-it shocks! I hate electricity!",
    63: "Oh, a pinball machine! I'll play for a while!",
    64: "Yay, perfect score! Looks like my EXP went way up!",
    65: "No, that was terrible... Am I bad at this?",
    66: "Is this a birdhouse? It looks interesting, so I'll check it out!",
    67: "I feel a little like a bird now! My EXP went up a little!",
    68: "Hmm, that wasn't interesting at all...",
    69: "Is that high-jump equipment? I wonder if I can clear it. I'll try!",
    70: "Yes, I made it! I'm so happy, and my EXP went up a fair bit!",
    71: "I couldn't clear it. That's a little disappointing...",
    72: "Hmm, that looks like a diving platform. I just jump from here, right?",
    73: "Whew, huge success! That felt great, and my EXP went way up!",
    74: "Nope, I changed my mind. That's scary!",
    75: "Is this a phonograph? It looks very old. I wonder if it still works.",
    76: "That's a pretty good song. I like it, and my EXP went up a little!",
    77: "It really is broken. That's too bad...",
    78: "This is a Holy Bell, right? I'll ring it!",
    79: "What a beautiful sound. It feels wonderful, and my EXP went up a fair bit!",
    80: "Hmm? It won't ring at all. Is it broken?",
    81: "This is Stonehenge, right? Maybe something good happens if I walk through it.",
    82: "Wow, amazing! Power's welling up, and my EXP went way up!",
    83: "Hmm? Nothing happened. That's disappointing.",
    84: "I wonder what's inside this...",
    85: "Whoa, this is dark medicine! My EXP went up a little!",
    86: "I-it feels creepy. Better leave it alone...",
    87: "What's this? It feels really eerie... A cursed box? I'll investigate.",
    88: "Amazing! This is dark power! My EXP went up a fair bit!",
    89: "Huh? The lid won't open. Never mind!",
    90: "Could this be a Dark Tower? Okay, I'll investigate!",
    91: "Whoa, dark power is surging through me! My EXP went way up!",
    92: "Hmm? Nothing happened. Maybe it isn't a Dark Tower.",
    93: "H-huh? What's that? Something nearby smells gentle and reassuring...",
    94: "Oh! Th-that's Taiki's scent! I hope we can play next time he visits. Our Friendship went up a little!",
    95: "Things have been peaceful and happy lately. It's all thanks to Taiki. H-he's a really good Tamer!",
    96: "Taiki, th-thank you for everything! We're so grateful. I hope that reached you. Our Friendship went way up!",
    97: "Hmm? What could this be...?",
    98: "Yay, I found 100 bits! I'll send them to Taiki right away. He'll be happy!",
    99: "Hmm? What could this be...?",
}
assert set(_BATCH_4L_ENTRY2) == set(range(100))
for _string_index, _localized_text in _BATCH_4L_ENTRY2.items():
    OVERRIDES[(5, 2, _string_index)] = _localized_text

_BATCH_4L_ENTRY3 = {
    0: "WOO! I found 500 bits! I'll send 'em to Taiki--he'll know what to do!",
    1: "WOO? What's this thing?",
    2: "WOO! A whole 1,000 bits! Taiki's gonna love this!",
    3: "WOO! A wild strawberry! Time for a taste test!",
    4: "Delicious! Now that's wild flavor! My EXP went up a little, too!",
    5: "Bleh! That strawberry was awful. What a letdown!",
    6: "WOO! That's one sturdy branch. Bet I can climb it!",
    7: "Made it! Nothing beats climbing high! My EXP went up a fair bit!",
    8: "So I climbed the tree... Now what? This is boring!",
    9: "WOO? A tree stump? What am I supposed to do with this?",
    10: "Not bad for weird training! My EXP went up a fair bit!",
    11: "Ow! This stump's covered in thorns! That's enough of that!",
    12: "WOO! Tasty tree sap! Let's find out if the name's true!",
    13: "Sweet! It really is delicious! My EXP went way up!",
    14: "Blech! That's horrible! Who called this stuff tasty?!",
    15: "Maximum HP increased! ^6 -> ^7",
    16: "Maximum MP increased! ^6 -> ^7",
    17: "Attack increased! ^6 -> ^7",
    18: "Defense increased! ^6 -> ^7",
    19: "Speed increased! ^6 -> ^7",
    20: "Friendship increased! ^6 -> ^7",
    21: "Spirit increased! ^6 -> ^7",
    22: "WOO! A scale! Time for the official weigh-in!",
    23: "Perfect weight! Looking good! My max HP went up a little, too!",
    24: "I'm overweight?! A fat wild Digimon's just a sweaty pig!",
    25: "WOO! A belt machine! Let's fire it up!",
    26: "That shaking feels great! My max HP went up a fair bit!",
    27: "It won't stop vibrating! Now I'm itchy all over!",
    28: "A treadmill! Time to run as hard as I can!",
    29: "Now that's a good sweat! My max HP went way up!",
    30: "Ugh... This feels nothing like real running. I'm gonna be sick!",
    31: "WOO? A crystal ball? It's totally clear inside.",
    32: "Whoa, it flashed! My max MP went up a little!",
    33: "Nothing happened. Boring!",
    34: "WOO! Tarot cards! Let's see what they can do!",
    35: "Magic power's surging through me! My max MP went up a fair bit!",
    36: "Nothing happened at all. What a boring deck!",
    37: "A pyramid! I've always wanted to go inside one!",
    38: "WOO! Pyramid power! My max MP went way up!",
    39: "No treasure, no curses, no traps? What a letdown!",
    40: "A punching bag! Finally, something I'm great at!",
    41: "WOO! Feel that power! My Attack went up a little!",
    42: "Ow! Guess I'm not in top form today.",
    43: "A training log! Time to hit it with everything I've got!",
    44: "Direct hit! My Attack went up a fair bit!",
    45: "Okay, my whole body's starting to hurt. That's enough!",
    46: "WOO! A giant boulder! Moving this'll be easy!",
    47: "That's my strongest power! My Attack went way up!",
    48: "It won't budge! Fine, the boulder wins this round!",
    49: "A punching machine? Bring it on!",
    50: "That was nothing! My Defense went up a little!",
    51: "Ow, ow, ow! This thing's impossible!",
    52: "A training cannon? WOO! Fire away!",
    53: "Nobody said it'd hurt that much! My Defense went up a fair bit!",
    54: "Endurance or not, that still hurts!",
    55: "Catch the iron ball? Bring it on!",
    56: "Caught it! I'm the strongest! My Defense went way up!",
    57: "The iron ball wins this time. Just this time!",
    58: "A bookshelf! Better have something fun in there!",
    59: "Reading can be fun sometimes! My Spirit went up a little!",
    60: "These books are way too hard. I can't read this stuff!",
    61: "A study desk? WOO... Please, anything but studying!",
    62: "I powered through it! My Spirit went up a fair bit!",
    63: "Nope! Even guts can't make this stuff possible!",
    64: "WOO! A magic circle! Let's see some magic!",
    65: "My mind's razor sharp! My Spirit went way up! I'm a genius!",
    66: "Huh. I really thought something would happen.",
    67: "Side-to-side jumps? I'm great at these!",
    68: "WOO! New record! My Speed went up a fair bit!",
    69: "Huff... I'm wiped out. Training over!",
    70: "A trampoline! Now this looks fun!",
    71: "I'm flying! WOO! My Speed went up a fair bit!",
    72: "Too much bouncing... I think I'm gonna be sick!",
    73: "A running wheel! Time to run wild!",
    74: "Now that's a workout! My Speed went way up!",
    75: "My body's spinning... My head's spinning... Everything's spinning!",
    76: "A Digimon keychain game! Let's give it a shot!",
    77: "WOO! Great game! Our Friendship went up a little!",
    78: "This is tougher than it looks. I'll get it next time!",
    79: "A cell phone! I'll send Taiki a message!",
    80: "Taiki replied! WOO! Our Friendship went up a fair bit!",
    81: "No reply? Aw, what a letdown.",
    82: "Taiki's digital camera! Time for one awesome self-portrait!",
}
assert set(_BATCH_4L_ENTRY3) == set(range(83))
for _string_index, _localized_text in _BATCH_4L_ENTRY3.items():
    OVERRIDES[(5, 3, _string_index)] = _localized_text

_BATCH_4M_ENTRY3 = [
    "WOO! Perfect shot! Our Friendship went way up!",
    "What?! I don't have a clue how to use this thing!",
    "WOO! A ring of fire! Jumping through it'll be easy!",
    "Nailed it! Body, spirit, and EXP--everything's burning up!",
    "N-no way! It's so hot I'm gonna burn to a crisp!",
    "A Fire Road?! Whoa, that's hot! I have to cross this thing?!",
    "I took the heat and made it! My EXP went up a fair bit!",
    "WOO! That's way too hot! This is impossible!",
    "Fireworks! All right, I'll launch 'em with a bang!",
    "WOO! Huge and awesome! My EXP shot way up, too!",
    "They won't even spark! Are the fireworks damp, or am I?!",
    "WOO! A giant ball! Time to roll around on this thing!",
    "This rules! It feels great, and my EXP went up a little!",
    "Why's everything spinning...? WOO! It's my eyes!",
    "WOO! A tightrope! I've always wanted to try this!",
    "Success! That was easier than I thought! My EXP went up a fair bit!",
    "WOO! I fell! And wow, did that hurt!",
]
assert len(_BATCH_4M_ENTRY3) == 17
for _string_index, _localized_text in enumerate(_BATCH_4M_ENTRY3, start=83):
    OVERRIDES[(5, 3, _string_index)] = _localized_text

_BATCH_4M_ENTRY4 = [
    "WOO! A circus tent! I'm gonna master every act in there!",
    "I feel reborn as a super performer! My EXP went way up!",
    "They made me clean the whole time. I didn't learn a thing...",
    "WOO! A mini shower! Perfect timing--I'm jumping in!",
    "That cold water feels awesome! My EXP went up a little!",
    "WOO! This water's freezing!",
    "A mini fishing pond! WOO! I'm gonna catch every fish!",
    "Fish on! I caught a tasty one, and some EXP, too!",
    "I didn't catch a thing. What a letdown!",
    "WOO! A huge waterfall! Time to train under it!",
    "Something amazing just clicked! My EXP went way up!",
    "Whoa, that's freezing! And it really hurts!",
    "WOO? Something smells great! Is it this flower?",
    "That nectar's sweet and delicious! My EXP went up a little!",
    "WOO! A good smell won't fill my stomach!",
    "A treehouse! Looks fun! I've decided--this is my house!",
    "Living with nature isn't bad! My EXP went way up!",
    "Nope! It looks cool, but living here is a huge pain!",
    "What the heck is this?! A computer? I wanna try it!",
    "Computers are awesome! I found a new world and gained EXP!",
    "No good! I'm a Digimon who's bad with digital stuff!",
    "WOO! I know this--a solar panel! Let's take a closer look!",
    "Electricity's flowing through me! My EXP went up a fair bit!",
    "WOO! I'm getting shocked! I can see my skeleton!",
    "A pinball machine! WOO! This looks like a blast!",
    "High score! I'm a genius! My EXP went way up!",
    "Why can't I win?! This machine has to be broken!",
    "What's this? A birdhouse? I'm gonna climb inside!",
    "WOO! I feel like a little bird! My EXP went up a little!",
    "It's cramped, smelly, empty, and boring in here!",
    "I know this--the high jump! Easy! Watch me fly!",
    "WOO! Cleared it with room to spare! My EXP jumped up, too!",
    "What the heck?! The only thing that flew was the bar!",
    "A diving platform! Easy! I'll soar like a bird!",
    "I flew! WOO! Just like a bird! My EXP floated way up!",
    "Nope! Turns out this bird's a total chicken!",
    "What the heck is this?! A phonograph? Does this old thing work?",
    "I like this sound! My EXP went up a little, too!",
    "It won't move at all! It's just a pile of junk!",
    "What the heck is a Holy Bell? I know the name, but that's it!",
    "WOO! I feel warm and fuzzy! Is this what 'holy' feels like?!",
    "It won't budge or ring. How am I supposed to know its sound?",
    "WOO! Stonehenge! Will something happen if I walk through?",
    "What the heck?! Is this holy power? My EXP went up!",
    "Wow. Absolutely nothing happened...",
    "WOO! Something's bubbling in this pot! Can I eat it?",
    "Dark medicine! WOO! My EXP went up a little!",
    "Blech! It stinks! Bitter, sour, nasty--this stuff's rotten!",
    "What's this creepy thing? A cursed box? What's inside?!",
    "WOO! Dark power! My EXP went up a fair bit!",
    "The lid won't open! Is that part of the curse?!",
    "Is this a Dark Tower? I'll get closer and find out!",
    "WOO! I feel strong dark power! My EXP went way up!",
    "What a letdown! All it did was put me in a dark mood!",
    "WOO? I smell something I really, really like!",
    "That's Taiki's scent! I wanna play when he comes back! Friendship went up!",
    "Life's easy and happy today! It's all thanks to Taiki!",
    "Taiki, you make us happy! Thanks! Our Friendship went way up!",
    "WOO! What the heck is this?!",
    "WOO! 100 bits! I'll send 'em to Taiki right away!",
    "WOO! What the heck is this?!",
    "WOO! I found 500 bits! I'll send 'em to Taiki right away!",
    "WOO! What the heck is this?!",
    "WOO! A whole 1,000 bits! I'll send 'em to Taiki right away!",
    "WOO! Wild strawberries! What a find!",
    "Sweet and tasty! My EXP went up!",
    "Blech! Bitter and sour--I can't eat this!",
    "WOO! I wanna climb a tree!",
    "Whoa! I climbed high and my EXP climbed with me!",
    "No good! It's too slippery to climb!",
    "What the heck is this?! Oh... It's just a tree stump.",
    "I rammed it and gained some EXP! Is this a magic mallet?!",
    "Ow! A splinter stabbed me and left my feelings splintered, too!",
    "WOO! Tasty tree sap! Time for a lick!",
    "Sweet and delicious! My EXP went way up!",
    "Nope! It tastes like raw grass. I can't lick this!",
    "Maximum HP increased! ^6 -> ^7",
    "Maximum MP increased! ^6 -> ^7",
    "Attack increased! ^6 -> ^7",
    "Defense increased! ^6 -> ^7",
    "Speed increased! ^6 -> ^7",
    "Friendship increased! ^6 -> ^7",
    "Spirit increased! ^6 -> ^7",
    "Hmm, a scale. I suppose I'll weigh myself.",
    "Hmph. I watch my weight, so no problem. My max HP went up a little.",
    "I'm overweight?! How could I let this happen...?",
    "A belt machine? It looks silly, but I'll give it a try.",
    "That was a better workout than expected. My max HP went up a fair bit.",
    "I-I can't stop shaking... That didn't go well.",
    "A treadmill. All right, I'll put some effort into a run.",
    "Exercise really does feel good. My max HP went way up.",
    "Pathetic... I can't believe that wore me out.",
    "A crystal ball. It's completely clear and rather beautiful.",
    "Did I just see something inside? My max MP went up a little.",
    "Nothing happened. Well, I suppose that's fine.",
    "Hmm? Are these tarot cards? Let's take a look.",
    "Magic power's flowing into me. My max MP went up a fair bit.",
    "Nothing happened. That's a little disappointing.",
    "A pyramid? Interesting. I'll take a look inside.",
    "Pyramid power is flowing into me! My max MP went way up!",
]
assert len(_BATCH_4M_ENTRY4) == 100
for _string_index, _localized_text in enumerate(_BATCH_4M_ENTRY4):
    OVERRIDES[(5, 4, _string_index)] = _localized_text

_BATCH_4M_ENTRY5 = [
    "I got completely lost... Damn, that's embarrassing.",
    "A punching bag. Perfect--I'll use it to train my attacks.",
    "I'm tired, but that felt good. My Attack went up a little.",
    "No good. It didn't go the way I wanted.",
    "A training log. Since it's here, I may as well use it.",
    "That went rather well. My Attack went up a fair bit!",
    "M-my whole body hurts... How pathetic.",
    "A giant boulder! Interesting. I'll move it myself.",
    "See? That was easy! My Attack went way up.",
    "Ugh... It's heavy. It won't move an inch.",
    "A punching machine? All right, come at me!",
    "Hmph. I still have plenty left. My Defense went up a little!",
    "Ow! Isn't this machine going a little too far?!",
    "A training cannon. Let's see what it can do.",
    "Success. That was no trouble. My Defense went up a fair bit!",
    "Ow! Take it easy, will you...?",
    "I see. I simply have to catch this iron ball!",
    "Hmph. That was nothing. My Defense went way up.",
    "N-no good! It hurts too much to endure!",
    "A bookshelf. Perhaps I'll read for the first time in a while.",
    "An interesting book calmed my mind. My Spirit went up, too.",
    "I'll save the reading for when I have more time.",
    "Why is there a study desk here? Not that I hate studying...",
    "Studying complete! My Spirit increased!",
    "...Fine, that was a lie. I hate studying!",
    "A magic circle? I wonder what sort of spell it uses.",
    "My head and mind feel clear! My Spirit went way up.",
    "If magic granted wishes instantly, nobody would need to work.",
    "Hmph, side-to-side jumps? Fine, I'll try them.",
    "That was nothing. My Speed went up a little!",
    "Huff, huff... That was harder than I expected.",
    "A trampoline. I suppose I'll relax and play for a while.",
    "The jumping was rather fun. My Speed went up a fair bit.",
    "No good... I bounced so much that I feel sick.",
    "A running wheel. Am I supposed to run inside this thing?",
    "Hmph. A good sweat felt nice. My Speed went way up.",
    "Ugh... N-no good. I'm getting dizzy.",
    "A Digimon keychain game. I may as well give it a try.",
    "More fun than I expected. Our Friendship went up a little!",
    "It's fun but difficult. I'll have to work harder.",
    "A cell phone. Perhaps I'll send Taiki a message.",
    "Taiki replied! Our Friendship went up a fair bit!",
    "No reply from Taiki. That's disappointing...",
    "Taiki left this digital camera. Maybe I'll take my picture.",
    "There. I hope Taiki sees it. Our Friendship went way up.",
    "Damn, I missed the shot. What a failure...",
    "A ring of fire. I have time, so I may as well try it.",
    "Hmph, success. That was easy. My EXP went up a fair bit.",
    "Ow! I messed that up...",
    "A Fire Road. If I stay calm, the heat should be no trouble.",
    "Hmph. This heat is nothing. My EXP went up a little.",
    "W-whoa, that's hot! No, this won't do...",
    "Fireworks. All right, I'll launch them myself.",
    "Not bad--they're beautiful! My EXP went way up!",
    "Nothing happened. Did I fail...?",
    "What a large ball. I suppose I'm meant to balance on it.",
    "Piece of cake. I mastered it, and my EXP went up a little.",
    "N-no good. I can't believe I failed something so simple.",
    "Could this be a tightrope? Interesting. I'll challenge it.",
    "Is that all? Easy. My EXP went up a fair bit.",
    "I-I failed? Me...?",
    "A circus tent. All right, I'll do some special training inside.",
    "Hmph. I cleared every act easily. My EXP went way up.",
    "Damn. That was harder than I expected...",
    "A mini shower. Perfect timing--I'll take a quick one.",
    "Ah, that's refreshing. My EXP went up a little.",
    "Ugh, freezing! I'll catch a cold at this rate!",
    "A mini fishing pond. I have time, so I'll give it a try.",
    "Hmph, I caught one. That's rather satisfying. My EXP went up.",
    "Nothing's biting... This is getting irritating!",
    "A large waterfall. Perfect--I'll train beneath it.",
    "My mind feels peaceful and calm. My EXP went way up.",
    "Ugh! What is this? It's much too cold!",
    "Hmm? What is that wonderful scent? It seems to be this flower.",
    "That fragrance is pleasant. My EXP went up a little.",
    "Whoa, a caterpillar?! I can't stand caterpillars!",
    "A treehouse. It seems pleasant. I'll live here for a while.",
    "Nature makes this place comfortable. My EXP went way up.",
    "Cramped, hot, and empty... This is more boring than expected.",
    "A computer. All right, I'll have a look at the internet.",
    "Now I understand how it works. My EXP went up a little.",
    "No good... I don't understand this machine at all.",
    "A solar panel? Interesting. I'll investigate it.",
    "Electricity's flowing through me. My EXP went up a fair bit.",
    "I-I'm numb! That experiment was a failure!",
    "A pinball machine? Hmph. A game now and then won't hurt.",
    "Look, a high score. That was easy. My EXP went way up.",
    "W-well, it was my first try. Of course I wasn't very good.",
    "A birdhouse? Interesting. I'll take a closer look.",
    "I think I understand birds a little better. My EXP went up.",
    "Unfortunately, I still don't see the appeal.",
    "A high-jump bar. Hmph, interesting. I'll try it.",
    "See? That was nothing. My EXP went up a fair bit.",
    "A failure... I still need more training.",
    "A diving platform? Interesting. I'll take the challenge.",
    "Hmph. I'm not afraid of this. My EXP went way up.",
    "Sorry... Let me try that another time.",
    "A phonograph. It's quite old, but does it still work?",
    "Good music. Very relaxing. My EXP went up a little.",
    "As I suspected, it's broken. That's a shame.",
]
assert len(_BATCH_4M_ENTRY5) == 100
for _string_index, _localized_text in enumerate(_BATCH_4M_ENTRY5):
    OVERRIDES[(5, 5, _string_index)] = _localized_text

_BATCH_4M_ENTRY6 = [
    "A Holy Bell. Since it's here, I may as well ring it.",
    "What a clear, beautiful sound. My EXP went up a fair bit.",
    "It won't make a sound. How disappointing.",
    "That appears to be Stonehenge. I'll take a closer look.",
    "Holy power is welling up inside me! My EXP went way up!",
    "So they're only ordinary ruins. How boring.",
    "What is this? I'll taste it and find out.",
    "Ugh, dark medicine! My EXP went up a little.",
    "B-bad! It tastes awful, and now I feel sick.",
    "What is this? It feels ominous... A cursed box?",
    "Such strong dark energy... My EXP went up a fair bit.",
    "The lid won't open. I suppose I'll give up.",
    "Could this be a Dark Tower? I'll go investigate.",
    "D-dark power is surging through me! My EXP went way up!",
]
assert len(_BATCH_4M_ENTRY6) == 14
for _string_index, _localized_text in enumerate(_BATCH_4M_ENTRY6):
    OVERRIDES[(5, 6, _string_index)] = _localized_text

_BATCH_4N_ENTRY6 = [
    "Nothing happened. Coming here was a waste of time.",
    "Hmm? A gentle, calming scent is coming from nearby...",
    "Hmph, that's Taiki's scent. I'll spend time with him when he returns.",
    "Peaceful days like this are all thanks to Taiki. I owe him.",
    "Taiki, you're the greatest Tamer. We're all grateful. Friendship went way up!",
    "Hmm? What's this?",
    "One hundred bits. I'll send them to Taiki. I hope they help.",
    "Hmm? What's this?",
    "Five hundred bits. I'll send them to Taiki. I hope he's pleased.",
    "Aha, what's this?",
    "A thousand bits! I'll send them to Taiki. He'll be pleased.",
    "Wild strawberries. I suppose I'll try a few.",
    "Sweet and delicious. My EXP went up a fair bit.",
    "These taste awful. I can't eat them.",
    "It looks like I can climb this tree.",
    "Hmph. That was easy. My EXP went up a little.",
    "Ugh, my hands are numb. I can't climb any farther.",
    "That's a large tree stump. What am I meant to do with it?",
    "I played around and gained some EXP. Wood can be comforting.",
    "Nothing happened. Not that I expected much from a stump.",
    "Could this be tasty tree sap?",
    "Surprisingly good. My EXP went way up.",
    "Tasty or not, it's still tree sap. Tree juice.",
    "Maximum HP increased! ^6 -> ^7",
    "Maximum MP increased! ^6 -> ^7",
    "Attack increased! ^6 -> ^7",
    "Defense increased! ^6 -> ^7",
    "Speed increased! ^6 -> ^7",
    "Friendship increased! ^6 -> ^7",
    "Spirit increased! ^6 -> ^7",
    "Oh, a scale? I don't need it. My weight control is flawless!",
    "See? My ideal weight, obviously! My max HP went up a little!",
    "W-what?! That's impossible! This scale is clearly broken!",
    "Oh, a belt machine. I suppose I'll let it exercise me a little.",
    "My figure's even better now! My max HP went up a fair bit!",
    "Wh-what is this?! I can't stop shaking!",
    "A treadmill? Why should someone like me have to run?",
    "Oh, I lost quite a bit! Fine by me! My max HP went way up!",
    "I'm too tired to move! I never want to do this again!",
    "What's this, a crystal ball? It's clear and rather beautiful.",
    "Did it just flash?! My max MP went up a little!",
    "If it shows nothing, it's no better than a glass ball.",
    "Oh, tarot cards! Now this might be interesting.",
    "What mysterious power! My max MP went up a fair bit!",
    "Fortunes don't interest me. Happiness is already my destiny!",
    "A pyramid? You expect me to go inside?",
    "Pyramid power made me stronger! My max MP went way up!",
    "It's damp and dark inside. This place is the absolute worst!",
    "A punching bag? I hate such barbaric activities!",
    "Oh, that was surprisingly satisfying! My Attack went up a little!",
    "No more! Sweaty training doesn't suit me at all!",
    "Is this a training log? Fine. If I must, I must...",
    "This is getting rather fun! My Attack went up a fair bit!",
    "My whole body hurts! This is the worst!",
    "What is this giant boulder?! Don't ask me to move that!",
    "Oh, it moved easily! Of course I'm amazing! My Attack went way up!",
    "See? It won't move. Exactly as I said!",
    "Is this a punching machine? You expect me to take that hit?",
    "Do you think this could hurt me? My Defense went up a little!",
    "Ow! What do you think you're doing?!",
    "A training cannon? How barbaric. Are we really doing this?",
    "For the record, that was nothing! My Defense went up a fair bit!",
    "That was dangerous! How rude!",
    "You expect me to catch this iron ball?!",
    "There, I did it! Satisfied? My Defense went way up!",
    "What are you doing?! Taiki, you're horrible!",
    "Oh, a bookshelf. I suppose I'll read for a little while.",
    "Reading is lovely. It calmed me down and raised my Spirit.",
    "I can't focus at all today. Forget it.",
    "A study desk? Are you actually telling me to study?",
    "My Spirit went up a fair bit--though I was already brilliant.",
    "Why should someone as brilliant and beautiful as me study?",
    "I know this. It's a magic circle, though it's only superstition.",
    "What is this? My mind keeps getting sharper! My Spirit went way up!",
    "See? Nothing happened. It's only superstition.",
    "Side-to-side jumps? Fine, I'll show you how they're done!",
    "Wasn't that elegant? My Speed went up a little!",
    "I twisted my ankle! Don't make me do such dull exercise!",
    "A trampoline? I'll show you my brilliant technique!",
    "Perfect. Completely flawless! My Speed went up a fair bit!",
    "Ow, I twisted my ankle! This is the worst!",
    "A running wheel? You expect me to run inside this ridiculous thing?",
    "That was better exercise than expected. My Speed went way up!",
    "This makes me look ridiculous! I'm never doing it again!",
    "Oh, a Digimon keychain game! Let me play!",
    "This is wonderful--the best! Our Friendship went up a little!",
]
assert len(_BATCH_4N_ENTRY6) == 86
for _string_index, _localized_text in enumerate(_BATCH_4N_ENTRY6, start=14):
    OVERRIDES[(5, 6, _string_index)] = _localized_text

_BATCH_4N_ENTRY7 = [
    "It's difficult, but still rather fun!",
    "Oh, a cell phone! I'll send Taiki a message. He should be grateful!",
    "He replied, as he should! Our Friendship went up a fair bit!",
    "Taiki didn't reply? He's the worst!",
    "Taiki left a digital camera. I'll let it take one picture of me!",
    "Perfect! It captured my beauty! Our Friendship went way up!",
    "Hey! Is this camera broken?!",
    "You expect me to jump through this ring of fire?",
    "There, success! That was easy. My EXP went up a fair bit!",
    "Eek! I hate this! I absolutely hate it!",
    "You expect me to cross this Fire Road?",
    "See? Easy for me! My EXP went up a little!",
    "Hot! This is the absolute worst!",
    "Oh, fireworks? You expect me to launch them?",
    "Lovely--almost as beautiful as me! My EXP went way up!",
    "They won't launch. How utterly disappointing.",
    "What's with this enormous ball? You want me to balance on it?!",
    "Hmph. Easy for me. My EXP went up a little!",
    "I can't stay on it at all! I've had enough!",
    "A tightrope? So you expect me to cross it.",
    "Did you see my elegant balance? My EXP went up a fair bit!",
    "This rope is too high, too thin, and far too shaky!",
    "A circus tent? I'll be a superstar wherever I perform!",
    "Everyone adored my charm! My EXP went way up!",
    "W-what was that training?! It was ridiculously hard!",
    "Oh, a mini shower. Perfect--I'll take a quick one.",
    "Ah, so refreshing! My EXP went up a little!",
    "Freezing! What is this?! My whole body's turning to ice!",
    "A mini fishing pond? Fine for passing the time.",
    "Even the fish surrender to my charm! My EXP went up a fair bit!",
    "Nothing's biting. I'm bored!",
    "A huge waterfall? You expect me to train under it?",
    "My mind feels totally refreshed. My EXP went way up!",
    "I've had enough! My hair is completely ruined!",
    "Oh, what a lovely fragrance. It seems to come from this flower.",
    "Beautiful looks and scent--just like me! My EXP went up a little!",
    "Eek, a caterpillar! This is the worst!",
    "A treehouse! This looks like the perfect home for me!",
    "Just as expected, it's wonderful! My EXP went way up!",
    "It's less convenient than expected. What a disappointment.",
    "Oh, a computer. Perhaps I'll browse the internet.",
    "I found some valuable information! My EXP went up a little!",
    "How do you even make this thing work?!",
    "A solar panel? And what exactly is so special about it?",
    "Electricity is charging me! My EXP went up a fair bit!",
    "W-wait, I'm getting shocked! Stop it!",
    "A pinball machine? I'll play to pass the time.",
    "It's more fun than expected! My EXP went way up!",
    "What's so interesting about this? I don't get it.",
    "A birdhouse? I do love beautiful little birds!",
    "There was a bird as beautiful as me! My EXP went up a little!",
    "Nothing was inside. Oh well.",
    "The high jump? Do you honestly think I can't clear that?",
    "Everyone adored my graceful jump! My EXP went up a fair bit!",
    "That one doesn't count! The bar was much too high!",
    "A diving platform? Fine! If I must jump, I'll jump!",
    "I-I wasn't scared! And my EXP went way up!",
    "I'll skip it today! N-not because I'm scared!",
    "Oh, a phonograph? It's terribly old. Does it work?",
    "Wonderful! It could be my theme song! My EXP went up a little!",
    "It won't move at all. It's merely a decoration.",
    "Oh, a Holy Bell! I'll make it ring beautifully!",
    "What a holy, beautiful sound! My EXP went up a fair bit!",
    "It won't ring. What is going on?!",
    "Stonehenge? I wonder what happens if I walk through.",
    "Holy power is welling up! My EXP went way up!",
    "Nothing happened. How disappointing.",
    "Ugh, what is this? It looks dreadful!",
    "Dark medicine?! At least my EXP went up a little.",
    "That's enough! Let's get out of here!",
    "W-what is this strange feeling? Is that a cursed box?!",
    "So this is dark power... My EXP went up a fair bit!",
    "This box won't open! F-fine, we'll leave it alone!",
    "Could this be a Dark Tower? Fine, I'll investigate it!",
    "No doubt--it's a Dark Tower! My EXP went way up!",
    "I don't feel anything. How dull.",
    "Oh? Something nearby smells incredibly sweet...",
    "That's Taiki's scent! I'll entertain him when he returns! Friendship went up!",
    "I've been so happy lately. Taiki deserves a special compliment!",
    "Taiki, you've done well! Keep serving me! Friendship went way up!",
    "Oh? What could that be?",
    "One hundred bits! I'll send them to Taiki. He'll be grateful!",
    "Oh? What could that be?",
    "Five hundred bits--lucky me! Taiki will admire me again!",
    "Oh? What could that be?",
    "One thousand bits! Taiki may worship me after this!",
    "Oh, delicious-looking wild strawberries! I'll try one.",
    "Quite tasty. They pass! My EXP went up a fair bit!",
    "Ptooey! So sour! Why would you make me eat that?!",
    "Oh, I could climb this tree.",
    "High places feel wonderful! My EXP went up a little!",
    "Don't make me do something so undignified!",
    "Oh? Is this a tree stump?",
    "It draws out my strength! My EXP went up a fair bit!",
    "I hit a stump and nothing happened. How utterly anticlimactic.",
    "Is that tasty tree sap? If it's really good, I'll try it.",
    "Oh, it truly is sweet and tasty! My EXP went way up!",
    "It's sticky and difficult to lick!",
    "Maximum HP increased! ^6 -> ^7",
    "Maximum MP increased! ^6 -> ^7",
]
assert len(_BATCH_4N_ENTRY7) == 100
for _string_index, _localized_text in enumerate(_BATCH_4N_ENTRY7):
    OVERRIDES[(5, 7, _string_index)] = _localized_text

_BATCH_4N_ENTRY8 = [
    "Attack increased! ^6 -> ^7",
    "Defense increased! ^6 -> ^7",
    "Speed increased! ^6 -> ^7",
    "Friendship increased! ^6 -> ^7",
    "Spirit increased! ^6 -> ^7",
    "Oh, a scale. I'm actually in the middle of a diet.",
    "I'm thinner than before! The diet worked, and my max HP went up!",
    "Oh no... I weigh far too much!",
    "A belt machine. I'll use it to tone my body.",
    "Whew, that was good exercise. My max HP went up a fair bit.",
    "I-I can't stop shaking. Did I overdo it?",
    "Oh, a treadmill. I'll run a little and continue my diet.",
    "Whew, I lost some weight! My max HP went way up.",
    "Ow! My leg cramped!",
    "A crystal ball. It's so beautiful, I feel drawn into it.",
    "It flashed, and I think I saw something! My max MP went up a little.",
    "Nothing happened. Perhaps it's only a decoration.",
    "Oh, tarot cards. Let's investigate them.",
    "I can feel magical power. My max MP went up a fair bit.",
    "But how are these used? I don't really understand.",
    "A pyramid. Since we're here, I'll look inside.",
    "I felt a strong, mysterious power! My max MP went way up!",
    "It's pitch-black inside. I can't see anything.",
    "Oh, a punching bag. I don't really enjoy attack training...",
    "I got carried away. How embarrassing. My Attack went up a little.",
    "As I thought, I dislike such rough behavior.",
    "A training log. Can a Digimon like me really do this?",
    "Oh, that went better than expected! My Attack went up a fair bit.",
    "No, I'm no good at this kind of thing.",
    "A giant boulder... There's no way I could move it.",
    "Oh? It moved more easily than expected. My Attack went way up!",
    "N-no, it really is impossible. It won't budge.",
    "I-is this a punching machine? I have to withstand the punch?",
    "It hurt, but I endured it. My Defense went up a little.",
    "Ow! It really hurts! Please stop!",
    "Oh, a training cannon. Am I supposed to catch the shot?",
    "Whew, I caught it somehow. My Defense went up a fair bit.",
    "Aah! It hurts too much to bear!",
    "I understand. I just need to catch this iron ball.",
    "Thank goodness, I caught it! My Defense went way up.",
    "I'm sorry, but this really is impossible for me...",
    "Oh, a bookshelf. I don't often get the chance to read here.",
    "Peaceful reading is wonderful! It nourished my mind and raised my Spirit.",
]
assert len(_BATCH_4N_ENTRY8) == 43
for _string_index, _localized_text in enumerate(_BATCH_4N_ENTRY8):
    OVERRIDES[(5, 8, _string_index)] = _localized_text

_BATCH_4O_ENTRY8 = [
    "I can't focus today. None of the words are sinking in.",
    "Oh, a study desk. It's been a while, so I'll sit down.",
    "I remember more than expected. My studying and Spirit improved.",
    "Oh dear... Why does sitting at a desk make me sleepy?",
    "A magic circle. Is it used for a spell?",
    "Magic or not, I feel much sharper. My Spirit went way up!",
    "It looks promising, but nothing happened.",
    "Side-to-side jumps. I'll give them a try!",
    "I'm actually good at these! My Speed went up a little!",
    "Oh... My body feels too heavy to jump well.",
    "A trampoline. Since it's here, let's play for a while.",
    "Floating through the air feels wonderful! My Speed went up a fair bit!",
    "Wh-what should I do? I'm too heavy to bounce very high.",
    "A running wheel. I'll get inside and run.",
    "Whew, what a good diet workout! My Speed went way up!",
    "I-I'm sorry. I'm too tired to move.",
    "Oh, a Digimon keychain game. I wonder if it's fun.",
    "It's like raising a child. How lovely! Friendship went up a little.",
    "I-it's difficult, though still fun.",
    "Oh, a cell phone. I wonder if I can message Taiki.",
    "Taiki replied! Our Friendship went up a fair bit!",
    "No reply. I must admit, I'm disappointed.",
    "Oh, Taiki's digital camera. I photograph rather well.",
    "Success! The picture is beautiful! Friendship went way up!",
    "Oh dear, I didn't take it in time.",
    "A ring of fire. It's frightening, but I'll try.",
    "Whew, I did it somehow! My EXP went up a fair bit.",
    "Aah! This is absolutely impossible for me!",
    "A Fire Road. You don't truly expect me to cross it...?",
    "Whew, I endured the heat. My EXP went up a little.",
    "Aah, it's hot! I can't stand it!",
    "Oh, fireworks. It would be a shame not to launch them.",
    "My, how beautiful! My EXP went way up!",
    "A failure? I'm too afraid to get closer.",
    "What a large ball. Am I supposed to stand on it?",
    "Balancing on it is fun! My EXP went up a little.",
    "Th-this is wobbly and very dangerous!",
    "A tightrope. I'm not confident, but I'll try.",
    "Thank goodness, I made it! My EXP went up a fair bit.",
    "I-it really is frightening. I'm sorry...",
    "A circus tent. Perhaps they'll teach me an act.",
    "They praised my performance! My EXP went way up!",
    "U-unfortunately, it seems I have no talent for this.",
    "Oh, a mini shower! I'm so happy--I love showers.",
    "Ah, I feel reborn! My EXP went up a little.",
    "B-but showering outdoors is embarrassing...",
    "A mini fishing pond. I wonder if I can catch anything.",
    "I did it! I caught one! My EXP went up a fair bit!",
    "Nothing's biting. I suppose it was impossible.",
    "A large waterfall. I'll train beneath it and strengthen my heart.",
    "I focused deeply and found peace. My EXP went way up.",
    "N-no, it hurts too much. I can't endure it!",
    "Oh, what a lovely scent. It seems to come from this flower.",
    "The more I look, the more beautiful it seems. My EXP went up.",
    "Aah, a caterpillar! N-no!",
    "A treehouse! Living somewhere like this has always been my dream!",
    "This house is truly wonderful! My EXP went way up!",
]
assert len(_BATCH_4O_ENTRY8) == 57
for _string_index, _localized_text in enumerate(_BATCH_4O_ENTRY8, start=43):
    OVERRIDES[(5, 8, _string_index)] = _localized_text

_BATCH_4O_ENTRY9 = [
    "Oh... Actually living here is rather inconvenient.",
    "Oh, a computer. I'll try connecting to the internet.",
    "There's so much information! My EXP went up a little.",
    "O-oh no! I think a virus got in!",
    "A solar panel. I believe it makes electricity from sunlight.",
    "It's true--I can feel electricity! My EXP went up a fair bit.",
    "Aah! My body is numb! I can't move!",
    "A pinball machine. I'm not very skilled at these...",
    "Oh, I think I understand the trick! My EXP went way up!",
    "No good. It's game over...",
    "A birdhouse. Let's peek inside for little birds.",
    "Baby birds were sleeping inside! My EXP went up a little.",
    "It was empty. That's a little disappointing.",
    "A high-jump bar. I don't think I can jump that high.",
    "I did it! I cleared it somehow! My EXP went up a fair bit!",
    "No, I couldn't do it. What a shame.",
    "Th-this is a diving platform. Do I really jump from here?",
    "Thank goodness! It was terrifying, but my EXP went way up!",
    "I-I'm sorry. I really can't do this!",
    "This is called a phonograph. It looks very old.",
    "My, what a wonderful sound! My EXP went up a little.",
    "As expected, it's broken. That's unfortunate.",
    "A Holy Bell. How lovely! I'd like to ring it.",
    "Just as I hoped, it sounds beautiful. My EXP went up a fair bit.",
    "Oh, it won't ring. How disappointing.",
    "This is Stonehenge. Should I walk between the stones?",
    "I feel powerful holy energy! My EXP went way up!",
    "Nothing happened. That's a little disappointing.",
    "S-something is boiling in there!",
    "O-oh, dark medicine! My EXP went up a little.",
    "N-no! I can't endure that smell!",
    "I feel an ominous presence. C-could this be a cursed box?",
    "Aah, such immense dark power! My EXP went up a fair bit.",
    "The lid won't open. That's a little disappointing.",
    "Could this really be a Dark Tower? I'll investigate more closely.",
    "Strong dark power is entering me! My EXP went way up!",
    "Nothing happened. It seems I was mistaken.",
    "Oh? A gentle, lovely scent is coming from nearby.",
    "It's Taiki's scent! I hope he'll visit again. Friendship went up!",
    "Our happy life is all thanks to Taiki. We should thank him.",
    "Taiki, thank you for everything! Our Friendship went way up!",
    "What could this possibly be?",
    "Oh, 100 bits! I'll send them to Taiki right away.",
    "What could this possibly be?",
    "Oh, 500 bits! I'll send them to Taiki right away.",
    "What could this possibly be?",
    "A thousand bits! I'll send them to Taiki right away.",
    "Oh, delicious-looking wild strawberries! I'll try some.",
    "Sweet and delicious! My EXP went up a fair bit.",
    "Much too sour! I can't eat them.",
    "Oh, it looks like I can climb this tree.",
    "I did it! I climbed successfully! My EXP went up a little.",
    "I'm sorry. I became too tired.",
    "That's a tree stump, isn't it?",
    "Its texture and firmness are perfect! My EXP went up a fair bit.",
    "The bark feels soft, but ramming it still hurts...",
    "Oh, tasty tree sap. I'll try a little.",
    "My, it's delicious! My EXP went way up!",
    "S-so bitter! That wasn't good at all!",
    "Maximum HP increased! ^6 -> ^7",
    "Maximum MP increased! ^6 -> ^7",
    "Attack increased! ^6 -> ^7",
    "Defense increased! ^6 -> ^7",
    "Speed increased! ^6 -> ^7",
    "Friendship increased! ^6 -> ^7",
    "Spirit increased! ^6 -> ^7",
    "Hmm? A scale. All right, I'll weigh myself.",
    "Weight control successful. My max HP went up a little.",
    "This weight is bad. I've gained far too much...",
    "A belt machine. I'll use it to tone my body.",
    "Whew. That was good exercise. My max HP went up a fair bit.",
    "Wh-what? My body won't stop shaking!",
    "Oh? A treadmill. I'll run for a while.",
    "Whew, that was demanding. My max HP went way up.",
    "Ow... I pushed too hard and twisted my ankle.",
    "A crystal ball? It's rather beautiful.",
    "Hmm?! I saw something inside! My max MP went up a little.",
    "Beautiful, but nothing more than that.",
    "Why are tarot cards sitting here?",
    "Hmm... I feel magical power! My max MP went up a fair bit.",
    "I don't know how to use or read tarot cards.",
    "A pyramid. I've always wondered what lies inside.",
    "What was that mysterious power?! My max MP went way up.",
    "I felt no power. It's too dark to see anything inside.",
    "Oh? A punching bag. Looking at it makes me want to strike.",
    "I nearly got carried away. My Attack went up a little.",
    "A punching bag never fights back. This alone isn't enough training.",
    "A training log? How exactly am I meant to use it?",
    "It worked better than expected. My Attack went up a fair bit.",
    "I don't understand. How does one train with this?",
    "A giant boulder. Surely training doesn't mean moving this?",
    "Hmm? It moved more easily than expected. My Attack went way up.",
    "I-it won't move at all.",
    "A punching machine. I must withstand its punch.",
    "Ow... I endured it somehow. My Defense went up a little.",
    "Aagh! Impossible! Absolutely impossible!",
    "A training cannon? Do I really have to catch that shot?",
    "Ugh, I caught it somehow. My Defense went up a fair bit.",
    "That's impossible. My body will break before my Defense improves.",
    "I simply have to catch this iron ball.",
]
assert len(_BATCH_4O_ENTRY9) == 100
for _string_index, _localized_text in enumerate(_BATCH_4O_ENTRY9):
    OVERRIDES[(5, 9, _string_index)] = _localized_text

_BATCH_4O_ENTRY10 = [
    "Good, I caught it! My Defense went way up!",
    "No. This is genuinely, absolutely impossible.",
    "A bookshelf? Well, a bookshelf truly is... a shelf for books.",
    "Ha! Reading now and then is nice. My Spirit went up a little.",
    "These books are far too difficult for me to read.",
    "A study desk? A challenge aimed at someone who hates studying!",
    "Studying complete! Spirit increased!",
    "I can live just fine without studying that much!",
    "A magic circle? Why is something like this here?",
    "Magic power made my Spirit go way up!",
    "Even magic couldn't make me smarter. I stare at my hands...",
    "Ugh, side-to-side jumps--my weakness!",
    "Yes! I did it! I can succeed when I try! Speed went up!",
    "Enough. If I push harder, my knees will snap.",
    "Oh, a trampoline. Since it's here, I'll play a little.",
    "Jump and bounce! My Speed went up a fair bit!",
    "Scary! The trampoline started creaking under me!",
    "A running wheel? You expect me to run inside it?",
    "The wheel rolled hard, and my Speed went way up!",
    "The force flung away my sweat, tears, dreams, and hopes...",
    "Oh, a Digimon keychain game. I wonder if it's fun.",
    "It's like raising a child. How lovely! Friendship went up a little.",
    "I-it's difficult, though still fun.",
    "Oh, a cell phone. I wonder if I can message Taiki.",
    "Taiki replied! Our Friendship went up a fair bit!",
    "No reply. I must admit, I'm disappointed.",
    "Oh, Taiki's digital camera. I photograph rather well.",
    "Success! The picture is beautiful! Friendship went way up!",
    "Oh dear, I didn't take it in time.",
    "A ring of fire? Hot, scary, and a little humiliating...",
    "All right, I did it! My EXP went up a fair bit!",
    "Why do I have to do things like this?",
    "A Fire Road? I have to cross this?",
    "Clear your mind and even fire feels cool! EXP went up!",
    "Hot! I'm burning, scorching, and catching fire!",
    "Fireworks. I suppose I should launch them with style.",
    "Brief, brilliant, beautiful fireworks! My EXP shot way up!",
    "Nothing but damp fireworks and a dreary life...",
    "What am I supposed to do with this huge ball?",
    "Good for training balance. My EXP went up a little.",
    "Danger! I'm falling, tumbling, toppling, and rolling!",
    "A tightrope? So I walk across the rope.",
    "Crossing a tightrope while crossing it raised my EXP!",
    "I crossed yet did not cross the tightrope. Or something.",
    "A circus tent? Am I meant to learn acrobatics inside?",
    "I learned acrobatics, and my EXP spun upward!",
    "Unfortunately, I wasn't suited for the circus.",
    "A mini shower. I suppose I'll take one for once.",
    "I got clean, and my EXP went up a little.",
    "Honestly, I'm really bad with showers.",
    "A mini fishing pond. Can I really catch fish here?",
    "Yes, I caught one! My EXP went up, too!",
    "Nothing bit. The rod never even twitched.",
    "A large waterfall. Am I meant to train beneath it?",
    "Waterfall training made my EXP go way up!",
    "I only got soaked. Nothing good happened.",
    "For some reason, this flower catches my attention.",
    "Beautiful shape, lovely scent. I relaxed and gained some EXP.",
    "It seems my interest was only my imagination.",
    "That's a rather pleasant-looking treehouse.",
    "Its cozy little form calms me. My EXP went way up.",
    "This kind of house is best admired from far away.",
    "A computer in a place like this? Lucky me!",
    "Search and research online! I gathered info and gained EXP!",
    "Using a computer felt productive, but only wasted my time.",
    "Oh, a solar panel! Can I generate solar power with it?",
    "Solar power gave me electricity, spirit, and EXP!",
    "Actually, I don't need electricity.",
    "Oh, a pinball machine!",
    "Yes! High score achieved, and EXP gained!",
    "Huh? I used to be better at this...",
    "A birdhouse in a place like this...",
    "The baby birds soothed me. My EXP went up a little.",
    "The parent bird pecked me. Mood down...",
    "The high jump. Honestly, I'm bad at it.",
    "Yes, success! My graceful jump made my EXP jump, too!",
    "It's not that I can't jump. I simply didn't want to.",
    "A diving platform? You expect me to jump from here?",
    "My EXP went way up, but my life got much shorter.",
    "Impossible. If I jump, I'll fall straight into the underworld.",
    "A phonograph?",
    "Beautiful music cleansed my heart and raised my EXP.",
    "It didn't move or make even the faintest sound.",
    "If I ring this Holy Bell, will I feel holy, too?",
    "Its beautiful sound made my EXP go up!",
    "The holy bell didn't ring, and I didn't feel holy.",
    "Stonehenge. I can feel strong power from it.",
    "Holy power made my EXP go way up.",
    "Nothing happened. Was it my imagination?",
    "Something is bubbling inside this suspicious pot.",
    "Strong dark power raised my EXP.",
    "It was only hot and smelly. Nothing happened.",
    "An ominous presence... Is this a cursed box?",
    "Whoa, what terrifying power! Dark energy raised my EXP!",
    "The presence left the box and came to me. Am I the cursed one?",
    "Could this be a cursed Dark Tower?",
    "Intense dark power. My EXP rose, but now I feel sick.",
    "Nothing happened, yet I still feel awful. That's the worst.",
    "Oh? A gentle, lovely scent is coming from nearby.",
    "It's Taiki's scent! I hope he'll visit again. Friendship went up!",
]
assert len(_BATCH_4O_ENTRY10) == 100
for _string_index, _localized_text in enumerate(_BATCH_4O_ENTRY10):
    OVERRIDES[(5, 10, _string_index)] = _localized_text

_BATCH_4O_ENTRY11 = [
    "Our happy life is all thanks to Taiki. We should thank him.",
    "Taiki, thank you for everything! Our Friendship went way up!",
    "What's this?",
    "Found 100 bits. I'll send them to Taiki.",
    "What's this...?",
    "Oh, 500 bits! I'll send them to Taiki right away.",
    "What's this...?",
    "Whoa, 1,000 bits! I'll send them to Taiki at once.",
    "I found some tasty-looking wild strawberries.",
    "Fresh, sweet, and tart! My EXP went up a fair bit!",
    "Bitter! Sour! And somehow grassy!",
    "These branches look perfect for climbing.",
    "Tree climb successful! My EXP went up a little!",
    "The branches creaked the whole time. That was terrifying.",
    "What's with this tree stump?",
    "Training with it felt comforting. My EXP floated upward.",
    "Ow... Were tree stumps always this hard?",
    "Found tasty tree sap. I'll try it right away.",
    "Surprisingly good. My EXP went way up.",
    "Awful! Does anyone honestly think this tastes good?",
    "Maximum HP increased! ^6 -> ^7",
    "Maximum MP increased! ^6 -> ^7",
    "Attack increased! ^6 -> ^7",
    "Defense increased! ^6 -> ^7",
    "Speed increased! ^6 -> ^7",
    "Friendship increased! ^6 -> ^7",
    "Spirit increased! ^6 -> ^7",
    "Oh yeah! A scale! Time to check my weight!",
    "I'm looking lean! Shape-up success! My max HP went up!",
    "Whoa, what happened?! My weight shot way up!",
    "A belt machine. Let's give this thing a try.",
    "Yeah! This really works! My max HP went up a fair bit!",
    "It only made my body jiggle. That didn't help at all!",
    "Oh, a treadmill! Time to tear up the track!",
    "Ha-ha! I'm the wind! My max HP blew way up!",
    "Failure, brother! This track doesn't take me anywhere!",
    "A crystal ball? Ha! Let's see the future!",
    "Whoa... I think I saw something! My max MP went up!",
    "I can't see a thing--not even tomorrow! Yeah!",
    "Oh yeah, tarot cards! Time to read my future!",
    "Is this magic power? My max MP went up a fair bit!",
    "Nothing happened! I don't believe in fortunes or spells!",
    "A pyramid. What's going on inside?",
    "Whoa! What is this power?! My max MP went way up!",
    "Nothing happened. It only smells like mold.",
    "A punching bag! Watch this, brother--I'll nail it!",
    "Ha-ha! How was that, brother? My Attack went up a little!",
    "I just heard a bone crack...",
]
assert len(_BATCH_4O_ENTRY11) == 48
for _string_index, _localized_text in enumerate(_BATCH_4O_ENTRY11):
    OVERRIDES[(5, 11, _string_index)] = _localized_text

_BATCH_4P_ENTRY11 = [
    "A training log? Perfect for some hard training, yeah!",
    "How was that sharp attack? My Attack went up a fair bit!",
    "No, this isn't my style. Bring me something cooler, yeah!",
    "What's with this boulder? Can anyone move it, brother?",
    "Whoa! Easier than expected! My Attack went way up, yeah!",
    "That's impossible. It won't budge.",
    "Found a punching machine! Looks quietly brutal, brother!",
    "Whoa, that hurts! I endured it, and my Defense went up!",
    "No way! This thing will knock the breath out of me!",
    "A training cannon? Don't tell me I have to catch the shot!",
    "Woo-hoo! I caught it! My Defense went up a fair bit!",
    "Nobody can catch a cannonball like that!",
    "Whoa, brother! I have to catch this?! I can do it!",
    "I did it, brother! Yes, I can! My Defense went way up!",
    "Nooo! I don't want this!",
    "A bookshelf? I suppose I'll read once in a while.",
    "Ha-ha! Just reading raised my Spirit a little, brother!",
    "Books are no good. They only made me sleepy.",
    "A study desk? Digimon have to study, too?!",
    "Yeah! My Spirit went up! I can do anything when I try!",
    "I can't do this. What a drag, brother!",
    "What's this again, a magic circle? How do you use it?",
    "My head cleared and my Spirit went up! It's magic, yeah!",
    "Nothing changed. If magic made everyone smart, Witchelny would be paradise!",
    "Side-to-side jumps? All right, let's do it!",
    "Did you see my speed, brother? Now it went even higher!",
    "Something just cracked in my back...",
    "A trampoline? Since it's here, I'll give it a try.",
    "Yeah! I can fly! My Speed went up, too!",
    "All this bouncing made me sick, brother!",
    "A running wheel? I have to run inside this?",
    "Ha-ha! My Speed went way up! I could run forever!",
    "Why am I spinning this thing alone? What's fun about that?!",
    "Oh, a Digimon keychain game! Looks fun--I'll try it!",
    "Easy and solid! Friendship went up! That's how I roll, man!",
    "It looks easy, but it's surprisingly hard!",
    "A cell phone. I'll give it a try.",
    "My hot conversation raised our Friendship!",
    "My signal didn't reach, or maybe the phone wasn't even on...",
    "Oh, a digital camera! Time to strike a cool pose!",
    "Yeah! Check out my profile! Friendship went up photogenically!",
    "Wait... Who is that ugly face supposed to be?",
    "Whoa, a ring of fire! That's pretty thrilling!",
    "Ha-ha, yeah! I can do it! My EXP burned upward!",
    "Something smells burned. Seriously, am I on fire?!",
    "Whoa, a Fire Road! I really have to cross that?",
    "Ha-ha! My fiery heart carried me across! My EXP rose a little!",
    "No way! My body and soul will burn out!",
    "Fireworks--a flower made of fire!",
    "They launched as boldly as I live! My EXP shot up, too!",
    "How old are these fireworks? They're completely damp!",
    "That's one huge ball. Maybe I can ride it...",
]
assert len(_BATCH_4P_ENTRY11) == 52
for _string_index, _localized_text in enumerate(_BATCH_4P_ENTRY11, start=48):
    OVERRIDES[(5, 11, _string_index)] = _localized_text

_BATCH_4P_ENTRY12 = [
    "Balance matters in everything! My EXP rose in perfect balance!",
    "That was dangerous, brother! I almost rolled instead of the ball!",
    "Oh, a tightrope? Watch me nail this!",
    "Easy success! My EXP went up a fair bit, yeah!",
    "Whoa, scary! Walking life's tightrope is enough for me, brother!",
    "A circus tent? Can I go inside?",
    "The crowd loved my moves! Great reviews and more EXP, yeah!",
    "I thought I could do anything, but I have no talent as a clown!",
    "Oh, a mini shower. Perfect--I'll take one.",
    "Yeah! Clean and refreshed! My EXP went up a little!",
    "Brrr, freezing! This thing only has cold water, brother!",
    "A mini fishing pond? Awesome! Fishing's my specialty!",
    "Yeah! Fish on! I caught a fish and some EXP!",
    "Nooo... Neither my rod nor my heart even twitched.",
    "A huge waterfall. Maybe I'll train my spirit beneath it!",
    "Body and soul tightened up! My EXP went way up, yeah!",
    "Ow, this hurts! My spirit will break before it gets stronger!",
    "That's a pretty nice flower.",
    "Beautiful and fragrant! Flowers are nice sometimes. EXP went up!",
    "It looks and smells nice, but what's the point, brother?",
    "A treehouse! This place looks great!",
    "Nice house, calming atmosphere! My EXP went way up!",
    "A tree house? Brother, this is just a shack.",
    "A computer! I've wanted one! Time to access the internet!",
    "Digimon need the internet, too! Knowledge, info, and EXP went up!",
    "I opened too many weird things and it froze. Help, brother!",
    "A solar panel! It makes electricity from sunlight, right?!",
    "Awesome! Electricity's charging! Energy and EXP gained!",
    "Electricity's crackling through me! What kind of punishment is this?!",
    "Why is there a pinball machine here?",
    "Ha-ha, I got the trick! My EXP went way up!",
    "Watching the pinball made my head spin.",
    "A birdhouse? If I try hard, maybe I can fit inside.",
    "If a bird can do it, so can I! Curiosity and EXP charged up!",
    "It's empty inside. A little disappointing, brother.",
    "Is this for the high jump? All right, let's do it!",
    "Yeah! High jump success! My EXP jumped up, too!",
    "For me, this is more like the 'can't-jump-high.'",
    "A diving platform? All right, brother! Watch this spin!",
    "Ha-ha! Maximum thrills! My EXP went up, too!",
    "No way! This is impossible--and dangerous, brother!",
    "A phonograph? It's ancient, but does it work?",
    "Whoa, that sound hits the heart! My EXP went up a little!",
    "It won't move, brother. No surprise--it's falling apart.",
    "A Holy Bell. Let's make it ring!",
    "Amazing--a truly holy bell! I could feel my EXP rising!",
    "It won't ring. Do I need a holier heart?",
    "Stonehenge? So I walk between those stones?",
    "Whoa, what immense power! My EXP rose, but my life may be shorter.",
    "Nothing happened, even after all that suspense.",
    "Ugh, what is this stinking pot?!",
    "Dark medicine! I feel awful, but my EXP went up a little!",
    "It smells so bad I'm getting dizzy!",
    "Hey, is this a cursed box?",
    "Dark power raised my EXP, but now I feel sick, brother.",
    "Nothing happened, yet I feel awful. Maybe I'm the cursed one!",
    "Whoa, a Dark Tower! It's scary, but I have to look!",
    "Dark power raised my EXP way up! Problem is, I feel cursed!",
    "Amazingly, absolutely nothing happened.",
    "Oh? A gentle, lovely scent is coming from nearby.",
    "It's Taiki's scent! I hope he'll visit again. Friendship went up!",
    "Our happy life is all thanks to Taiki. We should thank him.",
    "Taiki, thank you for everything! Our Friendship went way up!",
    "Hmm? What's this?",
    "Ha-ha! Got 100 bits! I'll send them to Taiki, yeah!",
    "Oh? What's this?",
    "Ha-ha! Got 500 bits! They're going to Taiki, brother!",
    "Hmm!",
    "We did it, brother! One thousand bits! I'll send them to Taiki!",
    "Wild strawberries! These look delicious, yeah!",
    "Sweet and tasty! My mood and EXP went up a fair bit!",
    "Bitter, hard, and sour! Are these really strawberries?!",
    "These branches look perfect for climbing.",
    "Yeah, I can do it! A little climb raised my EXP a little!",
    "Why am I climbing this? Calm down, brother.",
    "Found a tree stump...",
    "Whoa, what?! A light bump raised my EXP a fair bit!",
    "Tree stumps really aren't very useful.",
    "Tasty tree sap! It really does look delicious!",
    "Tasty and amazing! One lick sent my EXP upward!",
    "Good or bad, I don't really like tree sap.",
    "Maximum HP increased! ^6 -> ^7",
    "Maximum MP increased! ^6 -> ^7",
    "Attack increased! ^6 -> ^7",
    "Defense increased! ^6 -> ^7",
    "Speed increased! ^6 -> ^7",
    "Friendship increased! ^6 -> ^7",
    "Spirit increased! ^6 -> ^7",
]
assert len(_BATCH_4P_ENTRY12) == 88
for _string_index, _localized_text in enumerate(_BATCH_4P_ENTRY12):
    OVERRIDES[(5, 12, _string_index)] = _localized_text

def naturalize(text: str) -> str:
    for source, target in PLAIN_REPLACEMENTS:
        text = text.replace(source, target)
    text = text.replace("\r", "")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    text = text.replace("!?", "?!").replace("! ?", "?!")
    text = text.replace("? !", "?!").replace("! !", "!!").replace("? ?", "?!")
    text = re.sub(r"\bAll right\b", "All right", text, flags=re.IGNORECASE)
    contractions = (
        (r"\bI am\b", "I'm"),
        (r"\bI have\b", "I've"),
        (r"\bI will\b", "I'll"),
        (r"\bI cannot\b", "I can't"),
        (r"\bdo not\b", "don't"),
        (r"\bdoes not\b", "doesn't"),
        (r"\bdid not\b", "didn't"),
        (r"\bis not\b", "isn't"),
        (r"\bare not\b", "aren't"),
        (r"\bwas not\b", "wasn't"),
        (r"\bwere not\b", "weren't"),
        (r"\bwill not\b", "won't"),
        (r"\byou are\b", "you're"),
        (r"\bwe are\b", "we're"),
        (r"\bthey are\b", "they're"),
        (r"\bthat is\b", "that's"),
        (r"\bthere is\b", "there's"),
        (r"\bwhat is\b", "what's"),
        (r"\blet us\b", "let's"),
    )
    for pattern, replacement in contractions:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    # Frequent artifacts from literal Japanese suffixes and Google output.
    text = re.sub(r"\s+\b(a hoe|hoe)\b(?=[,.!?]|$)", "", text, flags=re.IGNORECASE)
    text = text.replace("Congratulations...?", "Congratulations!")
    text = text.replace("Everyone is ugly?!", "Is everyone okay?!")
    return text.strip()


def build(source: Path, output: Path, manifest: Path) -> dict[str, object]:
    replacements: dict[str, bytes] = {}
    changed = 0
    manual = 0
    with source.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        for archive_number, archive_name in enumerate(MESSAGE_ARCHIVES):
            pak = XrosPak.from_bytes(
                read_nitro_file(handle, find_nitro_file(files, archive_name))
            )
            entries: list[bytes] = []
            archive_changed = False
            for entry_index in range(len(pak.entries)):
                original = pak.unpacked_data(entry_index)
                try:
                    _offsets, strings = parse_message_table(original, encoding="shift_jis")
                except ValueError:
                    entries.append(original)
                    continue
                patched = list(strings)
                entry_changed = False
                for string_index, raw in enumerate(strings):
                    try:
                        text = raw.decode("ascii")
                    except UnicodeDecodeError:
                        continue
                    key = (archive_number, entry_index, string_index)
                    if key in OVERRIDES:
                        localized = OVERRIDES[key]
                        manual += 1
                    else:
                        localized = naturalize(text)
                    encoded = localized.encode("ascii", errors="replace")
                    if encoded != raw:
                        patched[string_index] = encoded
                        changed += 1
                        entry_changed = True
                entries.append(
                    build_message_table(original, patched) if entry_changed else original
                )
                archive_changed |= entry_changed
            if archive_changed:
                replacements[archive_name] = build_xros_pak(entries)
    rom = replace_nitrofs_files(source.read_bytes(), replacements)
    output.write_bytes(rom)
    result = {
        "source": str(source),
        "output": str(output),
        "output_sha256": hashlib.sha256(rom).hexdigest(),
        "changed_strings": changed,
        "hand_edited_strings": manual,
        "name_policy": "Japanese protagonist names retained",
        "locale": "en-US",
    }
    manifest.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.output, args.manifest), indent=2))
