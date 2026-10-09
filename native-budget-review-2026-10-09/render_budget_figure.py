"""Render a measured native-time SVG from two scalar-only audit projections."""
import argparse
import json
import math
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--earlier", type=Path, required=True)
    p.add_argument("--later", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--png-output", type=Path, help="Optional new PNG preview; requires matplotlib")
    a = p.parse_args()
    values = [json.loads(path.read_text()) for path in (a.earlier, a.later)]
    for value in values:
        if value.get("schema") != "gemma-native-budget-audit-v1":
            raise ValueError("Expected the scalar-only native audit schema")
    colors = ["#3b82f6", "#f97316", "#a78bfa", "url(#censored)"]
    labels = ["Completed root", "Failed root", "Completed compaction", "Unfinished (clock estimate)"]
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="1120" height="440" viewBox="0 0 1120 440">',
           '<defs><pattern id="censored" width="8" height="8" patternUnits="userSpaceOnUse"><rect width="8" height="8" fill="#e2e8f0"/><path d="M0 8 L8 0" stroke="#64748b" stroke-width="2"/></pattern></defs>',
           '<rect width="1120" height="440" fill="#f8fafc"/>',
           '<g font-family="Arial, sans-serif" fill="#0f172a">',
           '<text x="42" y="42" font-size="25" font-weight="bold">A healthy median can hide an exhausted task budget</text>',
           '<text x="42" y="70" font-size="15" fill="#475569">Two native canaries; 480-second active budget; both produced no patch or final JUnit.</text>']
    origin, width, axis_max = 145, 880, 500
    for n, value in enumerate(values):
        t = value["timing"]
        segments = [t["completed_model_seconds_including_compaction"] - t["completed_compaction_seconds"],
                    t["failed_model_seconds"], t["completed_compaction_seconds"],
                    t["censored_model_seconds_arm_clock_estimate"]]
        if any(isinstance(s, bool) or not isinstance(s, (float, int)) or not math.isfinite(s) or s < 0 for s in segments):
            raise ValueError("Invalid measured segments")
        y, cursor = 128 + 120 * n, origin
        svg.append(f'<text x="42" y="{y + 28}" font-size="18" font-weight="bold">V{19+n}</text>')
        for seconds, color in zip(segments, colors):
            w = seconds / axis_max * width
            svg.append(f'<rect x="{cursor:.3f}" y="{y}" width="{w:.3f}" height="42" fill="{color}"/>')
            if w > 100:
                svg.append(f'<text x="{cursor + w/2:.3f}" y="{y + 27}" font-size="15" text-anchor="middle">{seconds:.1f}s</text>')
            cursor += w
        median = t["completed_root_median_seconds"]
        longest = t["longest_finished_root_seconds"]
        share = 100 * t["longest_finished_root_budget_fraction"]
        svg.append(f'<text x="145" y="{y + 67}" font-size="14" fill="#475569">Completed-root median {median:.1f}s; longest finished root {longest:.1f}s ({share:.1f}% of budget)</text>')
    cap_x = origin + 480 / axis_max * width
    svg.append(f'<path d="M{cap_x:.3f} 108 V305" stroke="#0f172a" stroke-width="2" stroke-dasharray="5 4"/>')
    svg.append(f'<text x="{cap_x:.3f}" y="101" text-anchor="middle" font-size="13">480s cap</text>')
    for tick in (0, 100, 200, 300, 400, 500):
        x = origin + tick / axis_max * width
        svg.append(f'<text x="{x:.3f}" y="334" text-anchor="middle" font-size="13">{tick}s</text>')
    for n, (color, label) in enumerate(zip(colors, labels)):
        x = 42 + n * 270
        svg.append(f'<rect x="{x}" y="359" width="18" height="18" fill="{color}"/><text x="{x+26}" y="373" font-size="13">{label}</text>')
    svg += ['<text x="42" y="410" font-size="13" fill="#64748b">Unfinished duration uses the arm clock and is approximate. Latency is not an official score or a quality comparison.</text>', '</g></svg>']
    if a.output.suffix != ".svg":
        raise ValueError("Output must be a new SVG file")
    with a.output.open("x", encoding="utf-8") as stream:
        stream.write("\n".join(svg) + "\n")
    if a.png_output is not None:
        if a.png_output.suffix != ".png":
            raise ValueError("Preview must be a new PNG file")
        import os
        os.environ["MPLCONFIGDIR"] = str(a.png_output.parent / "matplotlib-cache")
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(12, 4.8), facecolor="#f8fafc")
        ax.set_facecolor("#f8fafc")
        for n, value in enumerate(values):
            t = value["timing"]
            segments = [t["completed_model_seconds_including_compaction"] - t["completed_compaction_seconds"],
                        t["failed_model_seconds"], t["completed_compaction_seconds"],
                        t["censored_model_seconds_arm_clock_estimate"]]
            cursor = 0
            for k, seconds in enumerate(segments):
                ax.barh(n, seconds, left=cursor, color=["#3b82f6", "#f97316", "#a78bfa", "#e2e8f0"][k],
                        height=.3, hatch="///" if k == 3 else None, edgecolor="#64748b" if k == 3 else None,
                        label=labels[k] if n == 0 else None)
                if seconds > 65:
                    ax.text(cursor + seconds/2, n, f"{seconds:.1f}s", ha="center", va="center", fontsize=11)
                cursor += seconds
            ax.text(0, n + .25,
                    f'Median {t["completed_root_median_seconds"]:.1f}s; longest finished root {t["longest_finished_root_seconds"]:.1f}s '
                    f'({100*t["longest_finished_root_budget_fraction"]:.1f}% of budget)', fontsize=10, color="#475569")
        ax.axvline(480, linestyle="--", color="#0f172a")
        ax.set_xlim(0, 500); ax.set_yticks([0, 1], labels=["V19", "V20"]); ax.invert_yaxis()
        ax.set_ylim(1.6, -.4)
        ax.set_xlabel("Seconds spent in model requests")
        ax.set_title("A healthy median can hide an exhausted task budget", loc="left", fontsize=16, pad=35)
        ax.legend(loc="upper left", bbox_to_anchor=(-.07, -.2), ncol=2, frameon=False)
        fig.text(.07, .035, "Two canaries; both produced no patch or final JUnit. Unfinished duration is a clock estimate, not completed latency.", fontsize=9, color="#64748b")
        fig.subplots_adjust(left=.08, right=.96, top=.72, bottom=.31)
        with a.png_output.open("xb") as stream:
            fig.savefig(stream, format="png", dpi=150, facecolor=fig.get_facecolor())
        plt.close(fig)


if __name__ == "__main__":
    main()
