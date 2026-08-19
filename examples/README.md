# Sample data files

This directory holds sample data for exercising Dream's data pipeline and
formatting features without any real customer data.

## `iranian-sales-sample.csv`

A small, hand-made sales extract with Persian headers (date, customer,
product category, product name, quantity, unit price in rial, and line
total in rial). All rows are fictional. The dates are Jalali (e.g.
`1404-05-14`), which is what a real Iranian ERP export looks like.

You can load it in a Dream data-science session and run the analysis tools
against it:

```text
load_data examples/iranian-sales-sample.csv
profile_data
analyze_data ...
```

The file is intentionally tiny (ten rows) so the full pipeline runs offline
and fast; the point is the shape of the data, not its size.
