import { fetchData } from './apiClient';
import type { ResearchRun } from '@/stores/researchStore';

/** Son araştırma panosu (diskten) — arayüz yeniden açılınca canlı olayları kaçırmış olabilir. */
export const fetchLastResearch = () => fetchData<ResearchRun>('/api/research/last');
