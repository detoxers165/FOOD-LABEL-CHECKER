import React, { createContext, useState, useEffect, useContext } from 'react';
import { getMe, logoutUser, updateProfile } from '../services/authApi';

const AuthContext = createContext();

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(localStorage.getItem('labelguard_token') || null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const initAuth = async () => {
      if (token) {
        try {
          const response = await getMe(token);
          setUser(response.data);
          setIsAuthenticated(true);
        } catch (error) {
          console.error("Token validation failed:", error);
          setToken(null);
          setUser(null);
          setIsAuthenticated(false);
          localStorage.removeItem('labelguard_token');
        }
      } else {
        setIsAuthenticated(false);
      }
      setIsLoading(false);
    };
    initAuth();
  }, [token]);

  const login = (newToken, newUser) => {
    setToken(newToken);
    setUser(newUser);
    setIsAuthenticated(true);
    localStorage.setItem('labelguard_token', newToken);
  };

  const logout = async () => {
    if (token) {
      try {
        await logoutUser(token);
      } catch (err) {
        console.error("Logout API failed:", err);
      }
    }
    setToken(null);
    setUser(null);
    setIsAuthenticated(false);
    localStorage.removeItem('labelguard_token');
  };

  const updateDisplayName = async (displayName) => {
    if (!token) return;
    const res = await updateProfile(token, displayName);
    setUser(res.data);
    return res.data;
  };

  const getAuthHeaders = () => {
    return token ? { 'Authorization': `Bearer ${token}` } : {};
  };

  return (
    <AuthContext.Provider value={{ user, token, isAuthenticated, isLoading, login, logout, updateDisplayName, getAuthHeaders }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
