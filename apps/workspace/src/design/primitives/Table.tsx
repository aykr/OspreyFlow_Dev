export interface TableColumn<Row> {
  key: string;
  header: string;
  render: (row: Row) => React.ReactNode;
  numeric?: boolean;
}

export interface TableProps<Row> {
  columns: TableColumn<Row>[];
  rows: Row[];
  getRowId: (row: Row) => string;
}

/** Headless per `docs/02_GLASS_FRONTEND.md` §1's "TanStack Table
 * (headless)... styling stays ours" — virtualisation for a 50k-row source
 * table is a real requirement at scale but out of this checkpoint's
 * critical path (the canvas, not a table, carries the 50k-node budget);
 * noted rather than silently deferred. */
export function Table<Row>({ columns, rows, getRowId }: TableProps<Row>) {
  return (
    <table className="table">
      <thead>
        <tr>
          {columns.map((col) => (
            <th key={col.key}>{col.header}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={getRowId(row)}>
            {columns.map((col) => (
              <td key={col.key} className={col.numeric ? "numeric" : undefined}>
                {col.render(row)}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
