/**
 * DEMO ONLY — delete this file + DemoUserSwitcher after the demo.
 * All accounts share VITE_DEMO_SEED_PASSWORD (same as DEV_SEED_PASSWORD).
 * Enable with VITE_DEMO_USER_SWITCH=1 in apps/web/.env.local.
 */

export type DemoUser = {
  email: string;
  name: string;
  role: 'coordinator' | 'director' | 'receptionist' | 'technician' | 'contractor';
};

/** Curated @sib.local seed accounts (shared demo password). */
export const DEMO_USERS: DemoUser[] = [
  { email: 'coordinator@sib.local', name: 'Charles Antoine Lessard', role: 'coordinator' },
  { email: 'director@sib.local', name: 'Charles Bergeron', role: 'director' },
  { email: 'receptionist@sib.local', name: 'Réception', role: 'receptionist' },
  { email: 'technician@sib.local', name: 'Alain Lepire', role: 'technician' },
  { email: 'jessie.thomassin@sib.local', name: 'Jessie Thomassin', role: 'technician' },
  { email: 'keith.proteau@sib.local', name: 'Keith Proteau', role: 'technician' },
  { email: 'zach.rousseau@sib.local', name: 'Zach Rousseau', role: 'technician' },
  { email: 'france.pichette@sib.local', name: 'France Pichette', role: 'technician' },
  { email: 'contractor@sib.local', name: 'Alexandre Thériault', role: 'contractor' },
  { email: 'mahmoud.chachia@sib.local', name: 'Mahmoud Chachia', role: 'contractor' },
  { email: 'miguel.tremblay@sib.local', name: 'Miguel Tremblay', role: 'contractor' },
];

export const DEMO_ROLE_GROUPS: { role: DemoUser['role']; fr: string; en: string }[] = [
  { role: 'coordinator', fr: 'Coordonnateurs', en: 'Coordinators' },
  { role: 'director', fr: 'Directeurs', en: 'Directors' },
  { role: 'receptionist', fr: 'Réception', en: 'Reception' },
  { role: 'technician', fr: 'Techniciens', en: 'Technicians' },
  { role: 'contractor', fr: 'Sous-traitants', en: 'Contractors' },
];

export function demoUserSwitchEnabled(): boolean {
  return import.meta.env.VITE_DEMO_USER_SWITCH === '1'
    || import.meta.env.VITE_DEMO_USER_SWITCH === 'true';
}

export function demoSeedPassword(): string {
  return (import.meta.env.VITE_DEMO_SEED_PASSWORD as string | undefined)?.trim() ?? '';
}
