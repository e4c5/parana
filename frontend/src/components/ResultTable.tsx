import { useState } from 'react';
import type { ResultPayload } from '../types';

interface Props {
  result: ResultPayload;
}

type SortDir = 'asc' | 'desc';

function isDeltaColumn(col: string): boolean {
  return col.toLowerCase().includes('delta');
}

function cellClass(col: string, value: unknown): string {
  if (!isDeltaColumn(col)) return '';
  const num = Number(value);
  if (isNaN(num) || num === 0) return '';
  return num > 0 ? 'positive' : 'negative';
}

export function ResultTable({ result }: Props) {
  const columns = result.columns ?? [];
  const rows = result.rows ?? [];

  const [sortCol, setSortCol] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<SortDir>('asc');

  function handleSort(col: string) {
    if (sortCol === col) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortCol(col);
      setSortDir('asc');
    }
  }

  const sorted = [...rows].sort((a, b) => {
    if (!sortCol) return 0;
    const av = a[sortCol];
    const bv = b[sortCol];
    const an = Number(av);
    const bn = Number(bv);
    const cmp = !isNaN(an) && !isNaN(bn) ? an - bn : String(av).localeCompare(String(bv));
    return sortDir === 'asc' ? cmp : -cmp;
  });

  return (
    <div className="result-table-wrapper">
      <table className="result-table">
        <thead>
          <tr>
            {columns.map((col) => (
              <th key={col} onClick={() => handleSort(col)} className="sortable-header">
                {col}
                {sortCol === col ? (sortDir === 'asc' ? ' ▲' : ' ▼') : ''}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row, i) => (
            <tr key={i}>
              {columns.map((col) => (
                <td key={col} className={cellClass(col, row[col])}>
                  {String(row[col] ?? '')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
