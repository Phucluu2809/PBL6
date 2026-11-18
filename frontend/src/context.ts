import { createContext, useContext } from 'react';
import type { Module, Permission, Role } from './types';
export const AppContext = createContext<{
  role: Role;
  notify: (s: string) => void;
  allowed: (m: Module, a?: Permission) => boolean;
}>({ role: 'Super Admin', notify: () => {}, allowed: () => false });
export const useApp = () => useContext(AppContext);
