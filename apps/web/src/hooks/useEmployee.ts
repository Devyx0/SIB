import { useState, useCallback } from 'react';

export function useEmployee() {
  const [employeeId, setEmployeeId] = useState<string | null>(() => {
    if (!import.meta.env.DEV) return null;
    return localStorage.getItem('dev_employee_id') ?? '4';
  });

  const setEmployee = useCallback((id: string | null) => {
    if (!import.meta.env.DEV) return;
    if (id) localStorage.setItem('dev_employee_id', id);
    else localStorage.removeItem('dev_employee_id');
    setEmployeeId(id);
  }, []);

  return { employeeId: import.meta.env.DEV ? employeeId : null, setEmployee };
}
