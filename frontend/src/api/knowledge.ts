/**
 * 知识库 API
 */
import { apiClient } from './client';

export interface KnowledgeItem {
  id: number;
  issue_title: string;
  issue_description: string;
  symptoms: string | null;
  root_cause: string | null;
  solution: string | null;
  effectiveness_score: number;
  severity: string | null;
  affected_system: string | null;
  category: string | null;
  tags: string | null;
  is_verified: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeCreateParams {
  issue_title: string;
  issue_description: string;
  symptoms?: string;
  root_cause?: string;
  solution?: string;
  effectiveness_score?: number;
  severity?: string;
  affected_system?: string;
  category?: string;
  tags?: string;
}

export interface KnowledgeUpdateParams extends Partial<KnowledgeCreateParams> {
  is_verified?: boolean;
}

export interface KnowledgeStats {
  total_incidents: number;
  verified_incidents: number;
  by_category: Record<string, number>;
  by_severity: Record<string, number>;
}

export const searchKnowledge = async (query: string, params?: {
  category?: string;
  severity?: string;
  limit?: number;
}): Promise<KnowledgeItem[]> => {
  const res = await apiClient.get('/v1/knowledge/search', { params: { query, ...params } });
  return res.data;
};

export const getKnowledgeList = async (params?: {
  category?: string;
  severity?: string;
  is_verified?: boolean;
  limit?: number;
  offset?: number;
}): Promise<KnowledgeItem[]> => {
  const res = await apiClient.get('/v1/knowledge/list', { params });
  return res.data;
};

export const getKnowledgeDetail = async (id: number): Promise<KnowledgeItem> => {
  const res = await apiClient.get(`/v1/knowledge/${id}`);
  return res.data;
};

export const createKnowledge = async (data: KnowledgeCreateParams): Promise<KnowledgeItem> => {
  const res = await apiClient.post('/v1/knowledge', data);
  return res.data;
};

export const updateKnowledge = async (id: number, data: KnowledgeUpdateParams): Promise<KnowledgeItem> => {
  const res = await apiClient.put(`/v1/knowledge/${id}`, data);
  return res.data;
};

export const deleteKnowledge = async (id: number): Promise<void> => {
  await apiClient.delete(`/v1/knowledge/${id}`);
};

export const getKnowledgeStats = async (): Promise<KnowledgeStats> => {
  const res = await apiClient.get('/v1/knowledge/stats/summary');
  return res.data;
};
