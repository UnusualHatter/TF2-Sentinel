# Sources

TF2 Sentinel keeps source provenance separate from the final confidence score. The table below describes the registered sources in the current repository snapshot.

A source with **Counts = no** is retained for reference, identity history, mirrors, or aggregation and does not independently increase confidence. **Records** is the number of rows bundled in this snapshot; a configured source can legitimately show `0` until its sync command is run.

<!-- sources-table:start -->
| ID | Source | Type | Region | Records | Weight | Counts | Link |
|---:|---|---|---:|---:|---:|:---:|---|
| 1 | CheaterList — friend association | tf2bd playerlist | global | 1,387 | 10 | yes | [upstream](https://github.com/d3fc0n6/CheaterList) |
| 2 | CheaterList — group association | tf2bd playerlist | global | 3,939 | 5 | yes | [upstream](https://github.com/d3fc0n6/CheaterList) |
| 3 | CheaterList — VAC + association | tf2bd playerlist | global | 647 | 20 | yes | [upstream](https://github.com/d3fc0n6/CheaterList) |
| 4 | TF2BD — official blacklist | tf2bd playerlist | global | 1,096 | 92 | yes | [upstream](https://github.com/PazerOP/tf2_bot_detector) |
| 5 | qfoxb — player list | tf2bd playerlist | global | 390 | 60 | yes | [upstream](https://github.com/qfoxb/tf2bd-lists) |
| 6 | MegaCheaterDB snapshot | tf2bd playerlist | mixed | 3,295 | 72 | yes | [upstream](https://mcdb.neocities.org/) |
| 7 | nullc0re — group membership | tf2bd playerlist | mixed | 121 | 8 | yes | [upstream](https://github.com/surepy/tf2db-sleepy-list) |
| 8 | RGL cheating bans — archived snapshot | tf2bd playerlist | mixed | 202 | 92 | yes | [upstream](https://github.com/surepy/tf2db-sleepy-list) |
| 9 | Sleepy bot list — Ivy | tf2bd playerlist | mixed | 7 | 55 | yes | [upstream](https://github.com/surepy/tf2db-sleepy-list) |
| 10 | Sleepy bot list — main | tf2bd playerlist | mixed | 453 | 72 | yes | [upstream](https://github.com/surepy/tf2db-sleepy-list) |
| 11 | Sleepy bot list — merged | tf2bd playerlist | mixed | 1,225 | 75 | yes | [upstream](https://github.com/surepy/tf2db-sleepy-list) |
| 12 | Sleepy bot list — MSB impersonators | tf2bd playerlist | mixed | 14 | 68 | yes | [upstream](https://github.com/surepy/tf2db-sleepy-list) |
| 13 | Sleepy bot list — Omegatronic | tf2bd playerlist | mixed | 181 | 68 | yes | [upstream](https://github.com/surepy/tf2db-sleepy-list) |
| 14 | Sleepy bot list — Perry | tf2bd playerlist | mixed | 13 | 60 | yes | [upstream](https://github.com/surepy/tf2db-sleepy-list) |
| 15 | Sleepy bot list — Pinkie | tf2bd playerlist | mixed | 22 | 60 | yes | [upstream](https://github.com/surepy/tf2db-sleepy-list) |
| 16 | Sleepy bot list — Pokerface | tf2bd playerlist | mixed | 194 | 40 | yes | [upstream](https://github.com/surepy/tf2db-sleepy-list) |
| 17 | Sleepy bot list — QT | tf2bd playerlist | mixed | 22 | 60 | yes | [upstream](https://github.com/surepy/tf2db-sleepy-list) |
| 18 | Sleepy bot list — Rosne | tf2bd playerlist | mixed | 55 | 60 | yes | [upstream](https://github.com/surepy/tf2db-sleepy-list) |
| 19 | Sleepy bot list — SIEC | tf2bd playerlist | mixed | 9 | 60 | yes | [upstream](https://github.com/surepy/tf2db-sleepy-list) |
| 20 | Sleepy bot list — Sydney | tf2bd playerlist | mixed | 114 | 65 | yes | [upstream](https://github.com/surepy/tf2db-sleepy-list) |
| 21 | Sleepy bot list — TF2Easy | tf2bd playerlist | mixed | 64 | 65 | yes | [upstream](https://github.com/surepy/tf2db-sleepy-list) |
| 22 | Sleepy bot list — Typical TF2 Player | tf2bd playerlist | mixed | 15 | 60 | yes | [upstream](https://github.com/surepy/tf2db-sleepy-list) |
| 23 | Sleepy bot list — Vinesauce | tf2bd playerlist | mixed | 62 | 65 | yes | [upstream](https://github.com/surepy/tf2db-sleepy-list) |
| 24 | Sleepy — external list | tf2bd playerlist | mixed | 167 | 35 | yes | [upstream](https://github.com/surepy/tf2db-sleepy-list) |
| 25 | Sleepy — miscellaneous | tf2bd playerlist | mixed | 104 | 20 | yes | [upstream](https://github.com/surepy/tf2db-sleepy-list) |
| 26 | Sleepy — no-proof list | tf2bd playerlist | mixed | 21 | 25 | yes | [upstream](https://github.com/surepy/tf2db-sleepy-list) |
| 27 | Sleepy — main list | tf2bd playerlist | mixed | 311 | 75 | yes | [upstream](https://github.com/surepy/tf2db-sleepy-list) |
| 28 | Rent-a-Medic — curated database | curated database | global | 0 | 88 | yes | [upstream](https://rentamedic.org/cheaters/) |
| 29 | Rent-a-Medic — community-ban index | aggregator | global | 0 | 0 | no | [upstream](https://rentamedic.org/cheaters/api) |
| 30 | Skial — SourceBans | sourcebans | global | 2,880 | 80 | yes | [upstream](https://www.skial.com/sourcebans/) |
| 31 | BlackWonder — SourceBans | sourcebans | global | 4,508 | 92 | yes | [upstream](https://bans.blackwonder.tf/index.php?p=banlist) |
| 32 | UGC — direct cheating bans | league bans | global | 0 | 90 | yes | [upstream](https://www.ugcleague.com/banlist_tf2.cfm) |
| 33 | UGC — mirrored bans | mirror index | global | 0 | 0 | no | [upstream](https://www.ugcleague.com/banlist_tf2.cfm) |
| 34 | Phoenix Gaming — community bans | community bans | global | 897 | 80 | yes | [upstream](https://bans.phoenix-gaming.gg/index.php?p=banlist) |
| 35 | Disc-FF — community bans | sourcebans | global | 2,141 | 82 | yes | [upstream](http://disc-ff.site.nfoservers.com/sourcebanstf2/index.php?p=banlist) |
| 36 | Panda Community — SourceBans | sourcebans | global | 4,871 | 90 | yes | [upstream](https://bans.panda-community.com/index.php?p=banlist) |
| 37 | Jump Academy — SourceBans | sourcebans | global | 900 | 80 | yes | [upstream](https://bans.jumpacademy.tf/index.php?p=banlist) |
| 38 | THG — community bans | community bans | global | 0 | 80 | yes | [upstream](https://rentamedic.org/cheaters/api) |
| 39 | LOOS Community — SourceBans | sourcebans | global | 898 | 92 | yes | [upstream](https://sb.looscommunity.com/?p=banlist) |
| 40 | GFL — community bans | community bans | global | 1,100 | 80 | yes | [upstream](https://rentamedic.org/cheaters/api) |
| 41 | Castaway.tf — SourceBans | sourcebans | global | 575 | 92 | yes | [upstream](https://castaway.tf/bans/index.php?p=banlist) |
| 42 | Serv dos Brother — SourceBans | sourcebans | south-america | 2,459 | 85 | yes | [upstream](https://bans.svdosbrothers.com/index.php?p=banlist) |
| 43 | Vovô Fortress — bans | community bans | south-america | 0 | 82 | yes | [upstream](https://vovo.tf/) |
| 44 | End of the Line — SourceBans | sourcebans | global | 431 | 80 | yes | [upstream](https://tf2.endofthelinegaming.com/sourcebans/) |
| 45 | ETF2L — cheating bans | league bans | europe | 210 | 92 | yes | [upstream](https://etf2l.org/etf2l/bans/) |
| 46 | RGL — cheating bans | league bans | north-america | 0 | 92 | yes | [upstream](https://rgl.gg/) |
| 47 | ozfortress — unfair-play bans | league bans | oceania | 0 | 92 | yes | [upstream](https://docs.ozfortress.com/info/anticheat_bans/) |
| 48 | Brasil Fortress — discipline | league bans | south-america | 0 | 90 | yes | [upstream](https://bf.sonikro.com/) |
| 49 | MetalStats.tf — MvM reputation | mvm reputation | global | 0 | 25 | yes | [upstream](https://metalstats.tf/) |
| 50 | Tacobot — MvM reports | mvm reputation | global | 0 | 12 | yes | [upstream](https://tacobot.tf/) |
| 51 | wgetJane — bot list | public playerlist | global | 3,025 | 60 | yes | [upstream](https://gist.github.com/wgetJane/0bc01bd46d7695362253c5a2fa49f2e9) |
| 52 | Milenko — Cathook broadcast list | public playerlist | global | 0 | 50 | yes | [upstream](https://github.com/PazerOP/tf2_bot_detector/wiki/Customization) |
| 53 | Valve — TF2 game-ban signal | platform ban | global | 0 | 45 | yes | [upstream](https://wiki.teamfortress.com/wiki/Game_ban) |
| 54 | Valve — VAC signal | platform ban | global | 0 | 30 | yes | [upstream](https://partner.steamgames.com/doc/webapi/isteamuser) |
| 55 | PLTF2C — community list | community list | global | 0 | 35 | yes | [upstream](https://steamcommunity.com/groups/PLTF2C/discussions/0/535151589910142184/) |
| 56 | TF2BD — Trusted list | tf2bd playerlist | global | 0 | 75 | yes | [upstream](https://github.com/PazerOP/tf2_bot_detector) |
| 57 | MTRN.hu — SourceBans | sourcebans | global | 313 | 90 | yes | [upstream](https://mtrn.hu/sourcebans/index.php?p=banlist) |
| 58 | MvM Lobby — reputation | mvm reputation | global | 0 | 18 | yes | [upstream](https://mvmlobby.tf/) |
| 59 | Rep.TF — reputation index | aggregator | global | 0 | 0 | no | [upstream](https://rep.tf/) |
| 60 | Horizon — Australia TF2 Cheaters | tf2bd playerlist | oceania | 296 | 75 | yes | [upstream](https://github.com/HorizonAUSanticheat/Australia-TF2-Cheaters) |
| 61 | Tom — Vorobey review database | reviewed report database | global | 4,217 | 92 | yes | [upstream](https://github.com/Nocrex/Tom) |
| 62 | bots.tf — bot list | compiled playerlist | global | 2,729 | 60 | yes | [upstream](https://bots.tf/) |
| 63 | CheaterList — friend association (compiled copy) | compiled playerlist | global | 1,387 | 10 | yes | [upstream](https://github.com/d3fc0n6/CheaterList) |
| 64 | Tacobot — compiled reports | compiled playerlist | global | 137 | 12 | yes | [upstream](https://tacobot.tf/) |
| 65 | TF2BD — official list (compiled copy) | compiled playerlist | global | 2,401 | 92 | yes | [upstream](https://github.com/PazerOP/tf2_bot_detector) |
| 66 | MCDB — cheaters | compiled playerlist | global | 3,248 | 72 | yes | [upstream](https://mcdb.neocities.org/) |
| 67 | MCDB — suspicious | compiled playerlist | global | 73 | 72 | yes | [upstream](https://mcdb.neocities.org/) |
| 68 | MCDB — watched | compiled playerlist | global | 1,033 | 72 | yes | [upstream](https://mcdb.neocities.org/) |
| 69 | MCDB — legit | compiled playerlist | global | 80 | 0 | no | [upstream](https://mcdb.neocities.org/) |
| 70 | SteamHistory — profile history | profile history enrichment | global | 0 | 0 | no | [upstream](https://steamhistory.net/) |
| 71 | minein4 — Shitlist | tf2bd playerlist | europe | 1,920 | 65 | yes | [upstream](https://github.com/minein4/Shitlist) |
| 72 | Garou3299 — TF2BD database | tf2bd playerlist | global | 229 | 70 | yes | [upstream](https://github.com/Garou3299/TF2BD-Database) |
| 73 | STAR Cheater Database | mirror index | global | 0 | 0 | no | [upstream](https://github.com/starshipsystems/tf2-cheater-list) |
| 74 | ill5 — MegaScatterBomb database mirror | mirror index | global | 0 | 0 | no | [upstream](https://github.com/ill5-com/megascatterbomb-tf2-cheater-database) |
| 75 | Nemesis — TF2BD player list | aggregator | global | 0 | 0 | no | [upstream](https://nemesis.surf/) |
| 76 | MegaAntiCheat — project reference | project reference | global | 0 | 0 | no | [upstream](https://github.com/oenu/MegaAntiCheat) |
| 77 | ZM Brasil — SourceBans | sourcebans | south-america | 793 | 90 | yes | [upstream](https://zmbr.mjsv.us/index.php?p=banlist) |
| 78 | Electric Servers — SourceBans | sourcebans | south-america | 0 | 90 | yes | [upstream](https://electricservers.com.ar/bans/) |
| 79 | Oppressive Territory — SourceBans | sourcebans | south-america | 109 | 85 | yes | [upstream](https://ban.optr.me/index.php?p=banlist) |
| 80 | TF2BD-ASEAN-LIST — player list | tf2bd playerlist | asia | 596 | 70 | yes | [upstream](https://github.com/Critical-Cookie/TF2BD-ASEAN-LIST) |
| 81 | joekiller — personal cheater list | tf2bd playerlist | north-america | 817 | 72 | yes | [upstream](https://github.com/joekiller/joekiller-list) |
| 82 | Vonny — personal cheater list | tf2bd playerlist | global | 15 | 50 | yes | [upstream](https://github.com/zyzel-del/blacklist_cheaters_tf2_bot_detector) |
| 83 | RednotePL — TF2 bot list | tf2bd playerlist | europe | 77 | 45 | yes | [upstream](https://github.com/RednotePL/tf2-botlist) |
| 84 | Cleffy — personal cheater list | tf2bd playerlist | europe | 1,096 | 72 | yes | [upstream](https://github.com/Cl3ffy/cleffy-list) |
| 85 | As0mn — NA casual cheater list | tf2bd playerlist | north-america | 449 | 65 | yes | [upstream](https://github.com/As0mn/tf2bd-list) |
| 86 | H0xton1337 — Naughty list | tf2bd playerlist | global | 762 | 60 | yes | [upstream](https://github.com/H0xton1337/naughtylist-) |
| 87 | DarkPyro's Servers — SourceBans | sourcebans | global | 184 | 85 | yes | [upstream](https://bans.darkpyro.gg/) |
| 88 | Flux.TF — SourceBans | sourcebans | global | 2,733 | 85 | yes | [upstream](https://bans.flux.tf/) |
| 89 | Scrap.TF — SourceBans | sourcebans | global | 2,216 | 82 | yes | [upstream](https://bans.scrap.tf/) |
| 90 | Titan.TF — SourceBans | sourcebans | global | 170 | 80 | yes | [upstream](https://bans.titan.tf/) |
| 91 | FirePowered — SourceBans | sourcebans | north-america | 2,610 | 82 | yes | [upstream](https://firepoweredgaming.com/) |
| 92 | The Furry Pound — SourceBans | sourcebans | global | 2,300 | 82 | yes | [upstream](https://sourcebans.thefurrypound.org/) |
| 93 | Otaku Gaming TF — SourceBans | sourcebans | global | 253 | 78 | yes | [upstream](https://bans.otaku.tf/) |
| 94 | TF2 Casual Fun — SourceBans | sourcebans | europe | 900 | 75 | yes | [upstream](https://tf2-casual-fun.de/) |
| 95 | UGC-Gaming.net — SourceBans | sourcebans | global | 4,517 | 80 | yes | [upstream](https://www.ugc-gaming.net/) |
| 96 | randomperson407 — player list | tf2bd playerlist | global | 62 | 40 | yes | [upstream](https://github.com/randomperson407/tf2bdplayerlist) |
| 97 | LBGaming — community bans | sourcebans | global | 327 | 78 | yes | [upstream](https://steamhistory.net/) |
| 98 | Liquid.tf — community bans | sourcebans | global | 147 | 78 | yes | [upstream](https://steamhistory.net/) |
| 99 | Pubs.tf — community bans | sourcebans | global | 151 | 78 | yes | [upstream](https://steamhistory.net/) |
| 100 | RetroServers.net — community bans | sourcebans | global | 162 | 78 | yes | [upstream](https://steamhistory.net/) |
| 101 | SG-Gaming — community bans | sourcebans | global | 1,107 | 78 | yes | [upstream](https://steamhistory.net/) |
| 102 | Sappho.io — community bans | sourcebans | global | 752 | 78 | yes | [upstream](https://steamhistory.net/) |
| 103 | dpg.tf — community bans | sourcebans | global | 1,799 | 78 | yes | [upstream](https://steamhistory.net/) |
| 104 | TF2 Sentinel — project annotations | project reference | global | 1 | 0 | no | [upstream](https://github.com/UnusualHatter/TF2-Sentinel) |
<!-- sources-table:end -->

## Notes

- Compiled copies and mirrors share an `independence_group` with their original source family, so the same underlying list cannot be counted twice.
- Generic VAC status is intentionally weaker than a TF2-specific reviewed or anti-cheat record because a VAC ban can come from another VAC-secured game.
- SteamHistory is identity-history enrichment only and contributes no confidence.
- South American server entries in `data/reference/south_america_servers.csv` are references. A server listing alone does not flag a player.
- Public SourceBans records are imported in full for provenance, but only bans whose stated reason is a cheating determination carry confidence weight. Association, alt-account detection, exploit abuse and conduct bans are recorded as `server_ban` and contribute nothing.
- TF2BD imports ignore unrelated behavior tags unless the record also contains a cheating-relevant classification.
- Some SourceBans sources reflect a recent-window sync (the most recent banlist pages only) rather than each community's full historical archive; their `last_verified` date marks when that sync was taken.

