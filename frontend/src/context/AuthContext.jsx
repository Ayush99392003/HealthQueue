import { createContext, useContext, useState, useCallback } from 'react';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try {
      const saved = localStorage.getItem('hq_user');
      return saved ? JSON.parse(saved) : null;
    } catch {
      return null;
    }
  });

  const login = useCallback((tokenData) => {
    const userData = {
      id: tokenData.user_id,
      role: tokenData.role,
      access_token: tokenData.access_token,
      refresh_token: tokenData.refresh_token,
    };
    localStorage.setItem('hq_token', tokenData.access_token);
    localStorage.setItem('hq_user', JSON.stringify(userData));
    setUser(userData);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('hq_token');
    localStorage.removeItem('hq_user');
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
