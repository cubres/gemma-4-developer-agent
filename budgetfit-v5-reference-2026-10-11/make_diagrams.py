# SPDX-License-Identifier: Apache-2.0
"""Original illustrative workflow diagrams; no measured results or new art."""
from pathlib import Path
import argparse
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

HERE = Path(__file__).resolve().parent / "generated_diagrams"


def draw(name, title, subtitle, nodes):
    fig, ax = plt.subplots(figsize=(12, 4.6))
    fig.patch.set_facecolor("#f5f3ff"); ax.set_facecolor("#f5f3ff")
    ax.set_xlim(0, 12); ax.set_ylim(0, 4.6); ax.axis("off")
    ax.text(.4, 4.05, title, fontsize=21, fontweight="bold", color="#26203d")
    ax.text(.4, 3.56, subtitle, fontsize=11, color="#625777")
    count = len(nodes); width = 10.7 / count - .2
    for index, (heading, detail) in enumerate(nodes):
        x = .4 + index * (width + .3)
        box = FancyBboxPatch((x, 1.0), width, 1.75, boxstyle="round,pad=0.04,rounding_size=.10",
                             linewidth=1.3, edgecolor="#8b78ad", facecolor="#ffffff")
        ax.add_patch(box)
        ax.text(x + .12, 2.38, heading, fontsize=12, fontweight="bold", color="#463163")
        ax.text(x + .12, 1.97, detail, fontsize=10, color="#4c4556", va="top", linespacing=1.5)
        if index < count - 1:
            ax.annotate("", xy=(x + width + .24, 2.0), xytext=(x + width + .04, 2.0),
                        arrowprops={"arrowstyle": "->", "color": "#8b78ad", "lw": 1.8})
    ax.text(.4, .54, "Illustrative workflow • exact source, native evidence and official scores stay separate",
            fontsize=10, color="#625777")
    for extension in ("png", "svg"):
        path = HERE / (name + "." + extension)
        if path.exists(): raise ValueError("New diagram path required")
        fig.savefig(path, dpi=170, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE,
                        help="A new directory; existing diagrams are preserved")
    HERE = parser.parse_args().output
    HERE.mkdir(parents=True, exist_ok=False)
    draw("reference_pipeline", "A released recipe you can reproduce", "Credited Budget-Fit V5; no policy or model substitution.", [
        ("01  Bind", "V5 source + ZIP\nFour member hashes\nAuthor and license"),
        ("02  Reproduce", "New output folder\nExact submission.zip\nNo agent executed"),
        ("03  Qualify", "Native compiler/serve\nTools + patch + grader\nSeparate clocks"),
        ("04  Evaluate", "Whole-run timing\nAccepted submission\nCompleted score")])
    draw("evaluation_contract", "What a canary can tell us", "One fixed, already exposed task establishes route readiness; it does not forecast leaderboard quality.", [
        ("Startup", "Wheel/model identity\nActual device contract\nReadiness deadline"),
        ("Agent", "8-minute policy cap\n28 calls / 80 turns\nOriginal prompt"),
        ("Verification", "240-second command\nOfficial task/scorer\nFailures retained"),
        ("Evidence", "Entered + returned\nBound private receipt\nNo score gain claim")])
    draw("cost_and_promotion", "Admission comes before allocation", "A machine-specific genuine bound is required; a guessed multiplier cannot approve a run.", [
        ("Source", "Exact model + runtime\nComplete demand\nPreserved identity"),
        ("Cost", "Fresh quota/inventory\nGenuine run ceiling\nUnknown → HOLD"),
        ("Native", "Owned deadline\nNo setup/scorer edits\nComplete outcomes"),
        ("Promotion", "Full runtime review\nOfficial completed row\nPublish verified result")])
