# Task: Xros Game Tester

Run the local working **Xros Evolution Complete US v3 UI+NAMES TEST** ROM in
DeSmuME. Do not modify the ROM, cheats, save data, or emulator settings.

1. Run `START_XROS_GAME_TESTER.cmd`.
2. Load the one displayed Lua script in DeSmuME and press **Run**.
3. Test the following screens once each: command ring, Live Events, a shop
   purchase confirmation, quest board, service menu, then complete one battle.
4. For every issue, take a screenshot and note: screen name, exact visible
   Japanese/clipped text, desired English, and whether navigation worked.
5. Press **Stop** in the Lua window.
6. Run `BUILD_XROS_GAME_TEST_REPORT.cmd`.

Return these items:

- `work/game-tester/xros/Xros_Game_Tester_Handoff.zip`
- screenshots of each failing screen
- a short issue list in this form:
  `Screen | exact problem | desired wording | blocks navigation? yes/no`

The handoff ZIP contains telemetry and save-state evidence only. It does not
contain a ROM, save file, or copyrighted game assets.
