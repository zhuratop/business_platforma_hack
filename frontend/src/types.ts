export type RunState = 'QUEUED'|'NORMALIZING'|'COMPARING'|'FACTS'|'CHECKS'|'STATS'|'REPORTING'|'READY'|'FAILED';
export type ChangeType = 'SAME'|'VALUE_CHANGED'|'ATTRIBUTE_NEW'|'ATTRIBUTE_LOST';
export interface Envelope<T> {id: string|null; status: string; data: T; error?: {code:string;message:string;details:unknown}}
export interface Run {id:string; status:RunState; progress:number; total:number; created:string; dataset_id:string; config_id:string; error?:string}
export interface PivotRequest {rows:string[];columns:string[];filters:Record<string,unknown[]>;measure:'unique_apps'}
export interface PivotCell {dimensions:Record<string,unknown>;count:number;cell_token:string}
export interface ComparisonRow {APP_ID:string;PATH:string;ARRAY_KEY:string;VALUE_BEFORE:string;VALUE_AFTER:string;ADJUSTED_BEFORE:string;ADJUSTED_AFTER:string;DIFF_FLAG:number;CHANGE_TYPE:ChangeType;PRESENT_BEFORE:boolean;PRESENT_AFTER:boolean;KIND_BEFORE:string;KIND_AFTER:string;highlight?:boolean}
