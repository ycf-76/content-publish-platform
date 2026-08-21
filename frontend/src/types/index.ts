export type NodeStatus = 'pending'|'running'|'awaiting_review'|'passed'|'rejected'|'error'|'suspended'|'completed'|'terminated'
export type NodeType = 'search'|'analyze'|'image_gen'|'image_review'|'copywrite'|'audit'|'final_review'|'publish'

export interface NodeSnapshot { node_id: string; node_type: NodeType; node_label: string; status: NodeStatus; order: number }
export interface WorkflowStarted { workflow_id: string; theme: string; keyword: string | null; account_nickname: string; started_at: string; nodes: NodeSnapshot[] }
export interface PendingReview { review_id: string; node_id: string; review_type: string; payload: any; created_at: string }
export interface WorkflowResponse { workflow_id: string; user_id: string; account_id: string; topic: string; status: string; current_node: string; created_at: string }
export interface AccountResponse { account_id: string; xhs_user_id: string; xhs_nickname: string; xhs_avatar_url: string; status: string; login_method: string }
export interface SSEEvent { event_id: string; type: string; payload: any; timestamp: string }

export type { Plugin, PluginCategory, PluginStatus, PricingModel, PluginStats, PluginVersion, PluginConfig, PluginReview, PluginListParams } from '@/api/plugins'