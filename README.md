# Dashboard Builder (example export)

A self-contained, read-only dashboard viewer built with Dashboard Builder, an offline, local-only dashboard tool in the spirit of Looker Studio: drop data + SQL into a `context/` folder, build a dashboard visually, export it as a standalone app like this one. This copy ships with an example dashboard, **Customers**, analyzing a sample customer dataset (counts by country, acquisition cost vs. customer count by segment, a US state choropleth, a gender breakdown) purely to demonstrate what an exported dashboard looks like - the tool itself works with any tabular data and SQL query you point it at.

No build step, no external services, nothing leaves your machine - just Flask, DuckDB, and a CSV file.

## Running it

```
pip install -r requirements.txt
python app.py
```

Then open http://localhost:5000.

## What's inside

- `app.py` / `config.py` - the Flask viewer app.
- `build/` - the rendering backend (Flask API blueprints, DuckDB query layer) and frontend (vanilla JS/HTML/CSS, ECharts for charts/maps).
- `context/` - the example data: `customer_master.csv` and the query that reads it, `customer.sql`.
- `build/dashboards/` - the dashboard definition (JSON) that ties queries to chart/table/filter layout.

This is a trimmed export containing only what's needed to view this one example dashboard - no editing UI, no other sample data.
