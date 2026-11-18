"""Draw actual assignments and measured traces; charts never decide service."""

from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.transforms import Bbox

from .models import Configuration, Scenario, SearchStep, ServiceResult


def _add_map_labels(figure, axes, labels, positions):
    """Place compact labels in free space without moving any scenario coordinates.

    Measure the actual rendered text, then try nearby offsets in a fixed order.
    Labels avoid earlier labels, all device/AP markers, and the plot edges when
    space permits. A thin leader connects each label to its original marker.
    Extremely dense custom scenarios may still need a larger map.
    """
    # Finalize the axes before measuring pixels; text must not resize them later.
    canvas = FigureCanvasAgg(figure)
    canvas.draw()
    renderer = canvas.get_renderer()
    marker_radius = 10 * figure.dpi / 72
    occupied = []
    for x, y in positions:
        pixel_x, pixel_y = axes.transData.transform((x, y))
        occupied.append(Bbox.from_bounds(pixel_x - marker_radius, pixel_y - marker_radius,
                                         2 * marker_radius, 2 * marker_radius))
    plot_bounds = axes.get_window_extent(renderer)

    for text, x, y, color, bold, prefer_above in labels:
        annotation = axes.annotate(
            text, (x, y), xytext=(0, 12), textcoords="offset points",
            fontsize=10, color=color, weight="bold" if bold else "normal",
            multialignment="center", zorder=6,
            bbox={"facecolor": "#f5f8fc", "edgecolor": "none", "alpha": 0.95, "pad": 1.5},
            arrowprops={"arrowstyle": "-", "color": "#98aabb", "lw": 0.6,
                        "shrinkA": 2, "shrinkB": 10},
        )
        annotation.set_in_layout(False)
        best_position = None
        best_overlap = float("inf")
        # Centered labels are easiest to scan. Try above/below first, then sides
        # and diagonals, expanding outward only when nearby labels collide.
        vertical = 1 if prefer_above else -1
        for distance in (12, 24, 36, 48, 60):
            offsets = [(0, vertical * distance), (0, -vertical * distance),
                       (distance, 0), (-distance, 0),
                       (distance, distance), (-distance, distance),
                       (distance, -distance), (-distance, -distance)]
            for offset_x, offset_y in offsets:
                horizontal_align = "left" if offset_x > 0 else "right" if offset_x < 0 else "center"
                vertical_align = "bottom" if offset_y > 0 else "top" if offset_y < 0 else "center"
                annotation.set_position((offset_x, offset_y))
                annotation.set_ha(horizontal_align)
                annotation.set_va(vertical_align)
                annotation.update_positions(renderer)
                annotation.update_bbox_position_size(renderer)
                bounds = annotation.get_bbox_patch().get_window_extent(renderer).padded(2)
                overlap = 0.0
                for obstacle in occupied:
                    intersection = Bbox.intersection(bounds, obstacle)
                    if intersection is not None:
                        overlap += intersection.width * intersection.height
                if not plot_bounds.fully_contains(bounds.x0, bounds.y0) or not plot_bounds.fully_contains(bounds.x1, bounds.y1):
                    overlap += 1_000_000  # Prefer an in-bounds label to clipped text.
                if overlap < best_overlap:
                    best_overlap = overlap
                    best_position = ((offset_x, offset_y), horizontal_align, vertical_align, bounds)
                if overlap == 0:
                    break
            if best_overlap == 0:
                break
        position, horizontal_align, vertical_align, bounds = best_position
        annotation.set_position(position)
        annotation.set_ha(horizontal_align)
        annotation.set_va(vertical_align)
        occupied.append(bounds)


def plot_layout(scenario: Scenario, configuration: Configuration, service: ServiceResult,
                failed_ap_id: str | None = None) -> Figure:
    """Map fixed devices/APs and real assignment lines; no invented coverage radii.

    Stars are critical devices, circles are guests, and squares are functioning
    APs. A cross identifies the failed AP. After failure only critical devices
    are required; unassigned guests are gray rather than mislabeled failures.
    """
    figure = Figure(figsize=(7, 4.5), layout="constrained")
    axes = figure.subplots()
    axes.set_facecolor("#f5f8fc")
    users = {user.user_id: user for user in scenario.users}
    access_points = {ap.ap_id: ap for ap in scenario.access_points}
    positions = [(user.x, user.y) for user in scenario.users] + [(ap.x, ap.y) for ap in scenario.access_points]
    labels = []
    for user_id, ap_id in service.assignments.items():
        user = users[user_id]
        ap = access_points[ap_id]
        axes.plot([user.x, ap.x], [user.y, ap.y], color="#9bb8cf", linewidth=1.2, zorder=1)

    for ap in scenario.access_points:
        failed = ap.ap_id == failed_ap_id
        axes.scatter(ap.x, ap.y, marker="X" if failed else "s", s=175,
                     color="#d04b46" if failed else "#173a59", zorder=4)
        label = f"{ap.ap_id}\nfailed" if failed else f"{ap.ap_id}\n{configuration[ap.ap_id]}"
        labels.append((label, ap.x, ap.y, "#173a59", True, True))

    for user in scenario.users:
        required = user.critical or failed_ap_id is None
        served = user.user_id in service.assignments
        color = "#0c8879" if served else ("#d04b46" if required else "#b6bec8")
        axes.scatter(user.x, user.y, marker="*" if user.critical else "o",
                     s=170 if user.critical else 65, color=color, edgecolors="white", zorder=5)
        labels.append((f"{user.user_id}\n{user.demand_mbps:g} Mbps", user.x, user.y,
                       "#314357", False, user.critical))

    axes.set_aspect("equal", adjustable="datalim")
    axes.margins(x=0.2, y=0.3)
    axes.grid(alpha=0.15)
    axes.set_xlabel("Local x position")
    axes.set_ylabel("Local y position")
    for side in ("top", "right"):
        axes.spines[side].set_visible(False)
    _add_map_labels(figure, axes, labels, positions)
    return figure


def plot_trace(history: list[SearchStep], unit: str) -> Figure:
    """Plot current and best complete objective values, with rejected trials visible."""
    figure = Figure(figsize=(8, 3), layout="constrained")
    axes = figure.subplots()
    axes.plot([item.step for item in history], [item.current_value for item in history],
              color="#668caf", linewidth=1, label="Current")
    axes.plot([item.step for item in history],
              [item.best_value if item.best_value is not None else float("nan") for item in history],
              color="#0c8879", linewidth=2, label="Best complete plan")
    rejected = [item for item in history if not item.accepted]
    axes.scatter([item.step for item in rejected], [item.candidate_value for item in rejected],
                 marker="x", color="#c48b49", s=12, alpha=0.5, label="Rejected proposal")
    axes.set_xlabel("Evaluated proposals (greedy: committed-change checkpoints)")
    axes.set_ylabel(unit)
    axes.grid(alpha=0.15)
    axes.legend(loc="best", fontsize=8)
    return figure


def plot_comparison(rows: list[dict]) -> Figure:
    """Compare normal Wh or recovery W; incomplete recovery bars are marked partial."""
    figure = Figure(figsize=(8, 3.5), layout="constrained")
    axes = figure.subplots()
    recovery = bool(rows) and "surviving_watts" in rows[0]
    value_key = "surviving_watts" if recovery else "energy_wh"
    colors = ["#9aabbc", "#1e5d82", "#0c8879"]
    for index, row in enumerate(rows):
        value = row.get(value_key)
        complete = row.get("complete", True)
        if value is None:
            axes.text(index, 0, "No plan", ha="center", va="bottom", fontsize=9)
        else:
            bar = axes.bar(index, value, color=colors[index % len(colors)], alpha=1 if complete else 0.4)
            if not complete:
                bar[0].set_hatch("//")
            axes.text(index, value, f"{value:g}" + (" · partial" if not complete else ""),
                       ha="center", va="bottom", fontsize=9)
    axes.set_xticks(list(range(len(rows))),
                     [row["method"].replace("Simulated annealing", "Annealing") +
                      (f"\n{row['critical_served']}/{row['critical_total']} critical" if recovery else "")
                      for row in rows])
    axes.set_ylabel("Surviving operating power (W)" if recovery else "Normal energy (Wh)")
    axes.margins(y=0.2)
    axes.spines["top"].set_visible(False)
    axes.spines["right"].set_visible(False)
    return figure
