import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { toast } from 'sonner';
import { Scale } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export default function Login({ setToken }) {
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      const endpoint = isLogin ? '/auth/login' : '/auth/register';
      const data = isLogin
        ? { email, password }
        : { email, password, full_name: fullName };

      const response = await axios.post(`${API}${endpoint}`, data);
      setToken(response.data.token);
      toast.success(isLogin ? 'Login realizado com sucesso!' : 'Conta criada com sucesso!');
      navigate('/cases');
    } catch (error) {
      toast.error(
        error.response?.data?.detail || 'Erro ao processar solicitação'
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex">
      <div
        className="hidden lg:flex lg:w-1/2 bg-cover bg-center relative"
        style={{
          backgroundImage:
            'url(https://images.unsplash.com/photo-1549791084-5f78368b208b?crop=entropy&cs=srgb&fm=jpg&q=85)',
        }}
      >
        <div className="absolute inset-0 bg-slate-900/60 backdrop-blur-sm" />
        <div className="relative z-10 flex flex-col justify-center p-12 text-white">
          <Scale className="w-16 h-16 mb-6" />
          <h1 className="text-4xl font-bold mb-4">Sistema de Acordos Judiciais</h1>
          <p className="text-lg text-slate-200">
            Gerencie acordos, parcelas e recebimentos de forma profissional e eficiente.
          </p>
        </div>
      </div>

      <div className="flex-1 flex items-center justify-center p-8">
        <div className="w-full max-w-md space-y-8">
          <div className="text-center">
            <Scale className="w-12 h-12 mx-auto mb-4 text-slate-900 lg:hidden" />
            <h2 className="text-3xl font-bold text-slate-900">
              {isLogin ? 'Entrar' : 'Criar Conta'}
            </h2>
            <p className="mt-2 text-sm text-slate-600">
              {isLogin
                ? 'Acesse sua conta para continuar'
                : 'Crie sua conta para começar'}
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-6" data-testid="login-form">
            {!isLogin && (
              <div>
                <Label htmlFor="fullName">Nome completo</Label>
                <Input
                  id="fullName"
                  type="text"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  required={!isLogin}
                  placeholder="Seu nome completo"
                  className="mt-1"
                  data-testid="fullname-input"
                />
              </div>
            )}

            <div>
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                placeholder="seu@email.com"
                className="mt-1"
                data-testid="email-input"
              />
            </div>

            <div>
              <Label htmlFor="password">Senha</Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                placeholder="••••••••"
                className="mt-1"
                data-testid="password-input"
              />
            </div>

            <Button
              type="submit"
              className="w-full bg-slate-900 hover:bg-slate-800"
              disabled={loading}
              data-testid="submit-button"
            >
              {loading ? 'Processando...' : isLogin ? 'Entrar' : 'Criar conta'}
            </Button>
          </form>

          <div className="text-center">
            <button
              type="button"
              onClick={() => setIsLogin(!isLogin)}
              className="text-sm text-blue-600 hover:text-blue-700 font-medium"
              data-testid="toggle-auth-mode"
            >
              {isLogin
                ? 'Não tem conta? Criar agora'
                : 'Já tem conta? Fazer login'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
