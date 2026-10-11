# SPDX-License-Identifier: MIT
"""Original conceptual SVG. Fixed toy values, no data or network dependency."""
import argparse
import html
from pathlib import Path

DATA = {'title': 'Verify before constructing a workspace', 'accent': '#7259ba', 'subtitle': 'Invented two-file flatpack · all payload text stays inert', 'cards': [['01 · PIN', 'Known manifest', 'Compare exact bytes with', 'an externally checked digest.'], ['02 · INVENTORY', 'All payload files', 'Count, size and hash each', 'manifested regular file.'], ['03 · PATH PLAN', 'Explicit complete map', 'Preserve literal __main__.', 'Do not guess from underscores.'], ['04 · OBSERVE', 'PASS_PINNED_BYTES', 'Wrong pin yields HOLD.', 'No files are restored or run.']], 'bottom_title': 'Separate gates after a byte check', 'bottom': [['Permission', 'Terms and package release need review.'], ['Native execution', 'Adapter, deadline and cleanup need receipts.'], ['Official outcome', 'Only the exact completed row supplies a score.']], 'footer': 'Consistency is not authentication or an atomic snapshot. Agent-package publication remains held.'}

def make_svg():
    d = DATA
    accent = d["accent"]
    e = html.escape
    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="1260" height="570" viewBox="0 0 1260 570" role="img">',
           '<title>'+e(d["title"])+'</title>',
           '<desc>'+e(d["subtitle"])+'</desc>',
           '<rect width="1260" height="570" rx="22" fill="#f5f8fa"/>',
           '<g font-family="Arial, sans-serif" fill="#172a38">',
           '<text x="34" y="48" font-size="27" font-weight="700">'+e(d["title"])+'</text>',
           '<text x="34" y="78" font-size="16" fill="#526572">'+e(d["subtitle"])+'</text>']
    for i, card in enumerate(d["cards"]):
        x = 34 + 307*i
        out += [f'<rect x="{x}" y="110" width="271" height="169" rx="15" fill="#fff" stroke="#d8e4e9"/>',
                f'<rect x="{x}" y="110" width="271" height="5" rx="2" fill="{accent}"/>']
        for j, text in enumerate(card):
            size = [14,20,16,16][j]
            y = [141,181,218,243][j]
            weight = '700' if j<2 else '400'
            color = accent if j==0 else '#172a38'
            out += [f'<text x="{x+17}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{color}">'+e(text)+'</text>']
        if i<3:
            start = x+278
            out += [f'<path d="M{start},194 h20 m-5,-5 l5,5 l-5,5" fill="none" stroke="{accent}" stroke-width="2.5"/>']
    out += ['<text x="34" y="320" font-size="21" font-weight="700">'+e(d["bottom_title"])+'</text>']
    if "bottom" in d:
        for i, (title, line) in enumerate(d["bottom"]):
            y=359+52*i
            out += [f'<circle cx="46" cy="{y-6}" r="5" fill="{accent}"/>',
                    f'<text x="64" y="{y}" font-size="18" font-weight="700">'+e(title)+'</text>',
                    f'<text x="285" y="{y}" font-size="17" fill="#526572">'+e(line)+'</text>']
    else:
        for i,(label,value) in enumerate(d["bars"]):
            y=342+48*i
            out += [f'<text x="34" y="{y+19}" font-size="16">'+e(label)+'</text>',
                    f'<rect x="265" y="{y}" width="560" height="28" rx="5" fill="#e3e9ed"/>']
            if value>0:
                out += [f'<rect x="265" y="{y}" width="{560*value:g}" height="28" rx="5" fill="{accent}"/>']
            out += [f'<text x="850" y="{y+20}" font-size="17" font-weight="700">{value:.1f}</text>']
    out += ['<path d="M34,503 H1226" stroke="#d8e4e9"/>',
            '<text x="34" y="537" font-size="16" fill="#526572">'+e(d["footer"])+'</text>', '</g></svg>']
    return "\n".join(out)+"\n"

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    if args.output.suffix.lower()!=".svg":
        parser.error("choose a fresh .svg file")
    # Exclusive creation preserves existing outputs, assets and notebook files.
    with args.output.open("x",encoding="utf-8") as f:
        f.write(make_svg())

if __name__=="__main__":
    main()
