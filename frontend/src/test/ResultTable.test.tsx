import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ResultTable } from '../components/ResultTable';
import type { ResultPayload } from '../types';

const SAMPLE: ResultPayload = {
  result_type: 'table',
  columns: ['entity_name', 'delta_covered_lines', 'coverage_pct_after'],
  rows: [
    { entity_name: 'com/Foo', delta_covered_lines: 3, coverage_pct_after: 0.8 },
    { entity_name: 'com/Bar', delta_covered_lines: -1, coverage_pct_after: 0.5 },
    { entity_name: 'com/Baz', delta_covered_lines: 0, coverage_pct_after: 0.6 },
  ],
};

describe('ResultTable', () => {
  it('renders the correct number of header columns', () => {
    render(<ResultTable result={SAMPLE} />);
    const headers = screen.getAllByRole('columnheader');
    expect(headers).toHaveLength(3);
    expect(headers[0]).toHaveTextContent('entity_name');
  });

  it('renders the correct number of data rows', () => {
    render(<ResultTable result={SAMPLE} />);
    const rows = screen.getAllByRole('row');
    // 1 header row + 3 data rows
    expect(rows).toHaveLength(4);
  });

  it('applies positive class to cells with positive delta', () => {
    const { container } = render(<ResultTable result={SAMPLE} />);
    const positiveCells = container.querySelectorAll('td.positive');
    expect(positiveCells.length).toBeGreaterThan(0);
    expect(positiveCells[0].textContent).toBe('3');
  });

  it('applies negative class to cells with negative delta', () => {
    const { container } = render(<ResultTable result={SAMPLE} />);
    const negativeCells = container.querySelectorAll('td.negative');
    expect(negativeCells.length).toBeGreaterThan(0);
    expect(negativeCells[0].textContent).toBe('-1');
  });

  it('sorts ascending by entity_name on first header click', () => {
    render(<ResultTable result={SAMPLE} />);
    fireEvent.click(screen.getByText('entity_name'));
    const cells = screen.getAllByRole('cell').filter((_, i) => i % 3 === 0);
    const names = cells.map((c) => c.textContent);
    expect(names).toEqual([...names].sort());
  });

  it('sorts descending on second click of same column', () => {
    render(<ResultTable result={SAMPLE} />);
    const header = screen.getByText('entity_name');
    fireEvent.click(header);
    fireEvent.click(header);
    const cells = screen.getAllByRole('cell').filter((_, i) => i % 3 === 0);
    const names = cells.map((c) => c.textContent ?? '');
    expect(names).toEqual([...names].sort().reverse());
  });

  it('sorts numerically by delta column', () => {
    render(<ResultTable result={SAMPLE} />);
    fireEvent.click(screen.getByText('delta_covered_lines'));
    const cells = screen.getAllByRole('cell').filter((_, i) => i % 3 === 1);
    const values = cells.map((c) => Number(c.textContent));
    for (let i = 0; i < values.length - 1; i++) {
      expect(values[i]).toBeLessThanOrEqual(values[i + 1]);
    }
  });

  it('renders empty table gracefully', () => {
    const empty: ResultPayload = { result_type: 'table', columns: ['a', 'b'], rows: [] };
    render(<ResultTable result={empty} />);
    expect(screen.getAllByRole('columnheader')).toHaveLength(2);
    // Only the header row
    expect(screen.getAllByRole('row')).toHaveLength(1);
  });

  it('renders gracefully when columns and rows are undefined', () => {
    const minimal: ResultPayload = { result_type: 'table' };
    render(<ResultTable result={minimal} />);
    expect(screen.getAllByRole('row')).toHaveLength(1); // header row only (no columns)
  });
});
