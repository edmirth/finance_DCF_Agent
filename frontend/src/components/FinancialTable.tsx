import { useRef, useState, type ReactNode } from 'react';
import { Download, Copy, Check } from 'lucide-react';

function extractTableData(table: HTMLTableElement): string[][] {
  const rows: string[][] = [];
  table.querySelectorAll('tr').forEach((tr) => {
    const cells: string[] = [];
    tr.querySelectorAll('th, td').forEach((cell) => {
      cells.push((cell as HTMLElement).innerText.trim());
    });
    if (cells.length > 0) rows.push(cells);
  });
  return rows;
}

function FinancialTable({ children }: { children: ReactNode }) {
  const tableRef = useRef<HTMLTableElement>(null);
  const [copied, setCopied] = useState(false);

  const handleExport = () => {
    if (!tableRef.current) return;
    const rows = extractTableData(tableRef.current);
    const csv = rows
      .map((row) =>
        row.map((cell) => {
          const escaped = cell.replace(/"/g, '""');
          return /[,"\n]/.test(cell) ? `"${escaped}"` : escaped;
        }).join(',')
      )
      .join('\n');

    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'table.csv';
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleCopy = async () => {
    if (!tableRef.current) return;
    const rows = extractTableData(tableRef.current);
    const tsv = rows.map((row) => row.join('\t')).join('\n');
    await navigator.clipboard.writeText(tsv);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="ft-wrap">
      <div className="ft-scroll">
        <table ref={tableRef} className="ft-table">
          {children}
        </table>
      </div>
      <div className="ft-actions">
        <button className="ft-btn" onClick={handleExport} title="Export CSV">
          <Download size={13} />
          Export
        </button>
        <button className="ft-btn-icon" onClick={handleCopy} title="Copy table">
          {copied ? <Check size={13} /> : <Copy size={13} />}
        </button>
      </div>
    </div>
  );
}

export const financialTableComponents = {
  table: ({ children }: { children?: ReactNode }) => (
    <FinancialTable>{children}</FinancialTable>
  ),
  thead: ({ children }: { children?: ReactNode }) => <thead>{children}</thead>,
  tbody: ({ children }: { children?: ReactNode }) => <tbody>{children}</tbody>,
  tr: ({ children }: { children?: ReactNode }) => <tr>{children}</tr>,
  th: ({ children, style }: { children?: ReactNode; style?: React.CSSProperties }) => (
    <th style={style}>{children}</th>
  ),
  td: ({ children, style }: { children?: ReactNode; style?: React.CSSProperties }) => (
    <td style={style}>{children}</td>
  ),
};

export default FinancialTable;
