"""Render an original explanatory SVG; fixed design allocation, not native data."""
from pathlib import Path
import sys

SVG = '''<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="520" viewBox="0 0 1100 520" role="img" aria-labelledby="title desc">
<title id="title">Leave time to finish</title>
<desc id="desc">A 480-second illustrative contract permits 390 seconds of exploration, then reserves 15 seconds to edit, 60 for targeted tests, 10 for patch capture, and 5 for settlement. Failed and unfinished calls remain visible. Native compatibility and score gain are unproven.</desc>
<rect width="1100" height="520" rx="24" fill="#101923"/>
<g font-family="system-ui, sans-serif" fill="#f1f6fa">
<text x="50" y="64" font-size="31" font-weight="650">Leave time to finish</text>
<text x="50" y="101" font-size="17" fill="#b8cad9">A deadline admission contract • original source-only proposal</text>
<text x="50" y="153" font-size="16">480 s agent-session budget</text>
<rect x="50" y="176" width="735" height="58" rx="7" fill="#397fb8"/>
<rect x="787" y="176" width="28" height="58" fill="#e6ab50"/>
<rect x="817" y="176" width="113" height="58" fill="#4eae97"/>
<rect x="932" y="176" width="19" height="58" fill="#ba92dc"/>
<rect x="953" y="176" width="9" height="58" fill="#8fa6b9"/>
<text x="73" y="212" font-size="20" font-weight="600">Explore ≤390 s</text>
<path d="M785 164 V244" stroke="#f1f6fa" stroke-width="2" stroke-dasharray="5 4"/>
<text x="663" y="270" font-size="15">Finish reserve begins</text>
<text x="50" y="310" font-size="17" fill="#e6ab50">Edit 15 s</text>
<text x="220" y="310" font-size="17" fill="#4eae97">Targeted tests 60 s</text>
<text x="465" y="310" font-size="17" fill="#ba92dc">Patch capture 10 s</text>
<text x="720" y="310" font-size="17" fill="#b8cad9">Settle 5 s</text>
<text x="50" y="356" font-size="17">Clamp every operation to remaining time • deny optional scouts / compaction</text>
<text x="50" y="389" font-size="17">Record COMPLETE, FAILED and UNFINISHED • fence cancellation survivors</text>
<text x="50" y="442" font-size="15" fill="#b8cad9">Illustrative allocation, not measured task requirements. External verification has a separate reserve.</text>
<text x="50" y="474" font-size="15" fill="#b8cad9">Native adapter compatibility: HOLD • Test success and leaderboard gain: unproven</text>
</g></svg>'''

if __name__ == "__main__":
    p = Path(sys.argv[1])
    if p.suffix != ".svg": raise ValueError("SVG output only")
    with p.open("x", encoding="utf-8") as f: f.write(SVG)
