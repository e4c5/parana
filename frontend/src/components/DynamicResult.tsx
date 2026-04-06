import type { ResultPayload } from '../types';
import { ResultTable } from './ResultTable';

interface Props {
  result: ResultPayload;
}

export function DynamicResult({ result }: Props) {
  if (result.result_type === 'table') {
    return <ResultTable result={result} />;
  }
  return null;
}
