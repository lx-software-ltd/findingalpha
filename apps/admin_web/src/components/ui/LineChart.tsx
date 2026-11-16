export type ChartPoint = { readonly x: string; readonly y: number };

export type ChartSeries = {
  readonly name: string;
  readonly colour: string;
  readonly points: readonly ChartPoint[];
};

const WIDTH = 640;
const PAD = 36;
const BOTTOM = 52;

export function LineChart({
  series,
  height = 220,
  formatY = (value: number) => value.toFixed(0),
  title,
}: {
  readonly series: readonly ChartSeries[];
  readonly height?: number;
  readonly formatY?: (value: number) => string;
  readonly title: string;
}) {
  const plotted = series.filter((item) => item.points.length > 0);
  if (plotted.length === 0) return <p>No series to plot.</p>;
  const values = plotted.flatMap((item) => item.points.map((point) => point.y));
  const low = Math.min(...values);
  const high = Math.max(...values);
  const span = high - low || 1;
  const ticks = [0, 1, 2, 3, 4].map((step) => low + (span * step) / 4);
  const yOf = (value: number) => height - BOTTOM - ((value - low) / span) * (height - PAD - BOTTOM);
  const xOf = (index: number, count: number) => PAD + (count <= 1 ? 0 : (index * (WIDTH - PAD * 2)) / (count - 1));
  const axis = plotted[0].points;
  const xTicks = [...new Set([0, 1, 2, 3, 4].map((step) => Math.round(((axis.length - 1) * step) / 4)))];

  return (
    <svg role="img" aria-label={title} viewBox={`0 0 ${WIDTH} ${height}`} className="w-100">
      {ticks.map((tick) => (
        <g key={tick}>
          <line x1={PAD} x2={WIDTH - PAD} y1={yOf(tick)} y2={yOf(tick)} stroke="#dee2e6" />
          <text x={0} y={yOf(tick) + 4} fontSize="11">
            {formatY(tick)}
          </text>
        </g>
      ))}
      {xTicks.map((index) => (
        <text key={axis[index].x} x={xOf(index, axis.length)} y={height - 6} fontSize="11" textAnchor="middle">
          {axis[index].x}
        </text>
      ))}
      {plotted.map((item) => (
        <path
          key={item.name}
          data-series={item.name}
          d={item.points
            .map((point, index) => `${index === 0 ? "M" : "L"} ${xOf(index, item.points.length)} ${yOf(point.y)}`)
            .join(" ")}
          fill="none"
          stroke={item.colour}
          strokeWidth="2"
        />
      ))}
      {plotted.map((item, index) => (
        <text key={item.name} x={PAD + index * 140} y={16} fontSize="12" fill={item.colour}>
          {item.name}
        </text>
      ))}
    </svg>
  );
}
