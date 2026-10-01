import { fetchData } from './apiClient';
import type { OfficeSnapshot, WorkerDetail } from '@/stores/officeStore';

// Ajan Ofisi uçları (backend/api/office.py) — hepsi salt-okunur.
export const fetchOfficeState = () => fetchData<OfficeSnapshot>('/api/office/state');

export const fetchWorkerDetail = (workerId: string) =>
  fetchData<WorkerDetail>(`/api/office/workers/${encodeURIComponent(workerId)}`);
