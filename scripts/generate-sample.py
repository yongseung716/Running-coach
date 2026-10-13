from datetime import datetime, timedelta, timezone
from pathlib import Path

start = datetime(2026, 1, 1, 6, tzinfo=timezone.utc)
points = []
for i in range(41):
    stamp = (start + timedelta(seconds=20*i)).isoformat()
    points.append(f'<trkpt lat="0" lon="{i*0.0005:.6f}"><ele>{10+i*0.5}</ele><time>{stamp}</time><extensions><hr>140</hr></extensions></trkpt>')
root = Path(__file__).resolve().parents[1]
(root / "samples/steady-2km.gpx").write_text('<?xml version="1.0"?><gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1"><trk><name>Synthetic test fixture — not a real run</name><trkseg>' + ''.join(points) + '</trkseg></trk></gpx>')
