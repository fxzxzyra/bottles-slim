"""Exercise Cairo drawing and theme colors without physical graphics hardware."""

import cairo
import pytest

from bottles.frontend.widgets.playtimechart_hourly import PlaytimeChartHourly
from bottles.frontend.widgets.playtimechart_weekly import PlaytimeChartWeekly
from bottles.frontend.widgets.playtimechart_monthly import PlaytimeChartMonthly


@pytest.mark.parametrize("kind, setter, labels, count", [
    (PlaytimeChartHourly, "set_hourly_data", "_draw_hour_labels", 24),
    (PlaytimeChartWeekly, "set_daily_data", "_draw_day_labels", 7),
    (PlaytimeChartMonthly, "set_monthly_data", "_draw_month_labels", 12),
])
def test_chart_draws_data_instead_of_only_empty_grid(kind, setter, labels, count):
    chart = kind()

    def render(minutes):
        getattr(chart, setter)([minutes] * count, max_hours=2)
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 640, 200)
        context = cairo.Context(surface)
        chart._draw_chart(None, context, 640, 200)
        getattr(chart, labels)(None, context, 640, 30)
        surface.flush()
        return bytes(surface.get_data())

    empty = render(0)
    populated = render(60)
    assert populated != empty
    assert any(populated)
