"""Small synthetic HURDAT2 files in the official format (trailing wind-radii columns omitted)."""

# ALPHA: moves due north along 80.0W, passing ~19 km east of Miami on 2020-08-01.
# BETA:  far out in the central Atlantic on 2020-09-15.
# GAMMA: two fixes ~380 km either side of Miami; only interpolation reveals the pass.
ATLANTIC = """\
AL012020,              ALPHA,      4,
20200801, 0000,  , TS, 24.0N,  80.0W,  50, 1000,
20200801, 0600,  , HU, 25.0N,  80.0W,  70,  990,
20200801, 1200,  , HU, 26.0N,  80.0W,  90,  980,
20200801, 1800,  , EX, 27.0N,  80.0W,  40, 1005,
AL022020,               BETA,      2,
20200915, 0000,  , TD, 15.0N,  40.0W,  30, 1009,
20200915, 0600,  , TS, 15.5N,  41.0W,  35, -999,
AL032020,              GAMMA,      2,
20201001, 0000,  , TS, 25.8N,  84.0W,  45,  998,
20201001, 0600,  , TS, 25.8N,  76.0W,  45,  998,
"""

PACIFIC = """\
EP012020,              DELTA,      2,
20200701, 0000,  , HU, 15.0N, 110.0W, 100,  960,
20200701, 0600,  , ET, 15.5N, 181.0W,  -99, -999,
"""
