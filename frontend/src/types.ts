export type Role = 'Super Admin' | 'Admin' | 'Operator' | 'Researcher' | 'Viewer' | 'Tester';
export type UserStatus = 'Active' | 'Locked' | 'Disabled' | 'Pending';
export interface User {
  id: string;
  name: string;
  email: string;
  department: string;
  title: string;
  phone: string;
  roles: Role[];
  status: UserStatus;
  mfa: boolean;
  lastLogin: string;
  group: string;
}
export interface Sample {
  id: string;
  person: string;
  name?: string;
  date: string;
  qc: 'PASS' | 'REVIEW' | 'FAIL';
  duration: number;
  device: string;
  protocol: string;
  note: string;
  readOnly?: boolean;
  sourcePath?: string;
  qcSource?: string;
  rowCount?: number;
  bytes?: number;
  phases?: string[];
  channels?: { key: string; label: string; unit: string }[];
  schema?: string;
  processStatus?: string;
}
export interface Person {
  id: string;
  name: string;
  consent: boolean;
  note: string;
}
export interface Audit {
  id: string;
  actor: string;
  action: string;
  target: string;
  time: string;
}
export interface Invitation {
  id: string;
  email: string;
  role: Role;
  status: 'Pending' | 'Accepted' | 'Expired' | 'Revoked';
  date: string;
}
export interface Model {
  id: string;
  name: string;
  version: string;
  channels: string;
  metrics: string;
  active: boolean;
  date: string;
}
export interface AIResult {
  id: string;
  sample: string;
  model: string;
  kind: 'Nhận diện' | 'Matching';
  result: string;
  score: number;
  time: string;
}
export type Permission = 'view' | 'create' | 'edit' | 'delete' | 'control' | 'export' | 'manage';
export type Module =
  | 'testing'
  | 'dashboard'
  | 'devices'
  | 'experiments'
  | 'samples'
  | 'people'
  | 'ai'
  | 'models'
  | 'users'
  | 'roles'
  | 'security'
  | 'settings'
  | 'reports'
  | 'profile';
export type PermissionMatrix = Record<Role, Record<Module, Permission[]>>;
export interface Store {
  users: User[];
  samples: Sample[];
  people: Person[];
  invitations: Invitation[];
  audits: Audit[];
  models: Model[];
  results: AIResult[];
  permissions: PermissionMatrix;
  settings: Record<string, string>;
}
