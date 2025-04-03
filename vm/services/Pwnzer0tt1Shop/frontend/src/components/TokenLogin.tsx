import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { tokenLoginRequest } from '../utils/net';
import { useQueryClient } from '@tanstack/react-query';
import { MainLayout } from './MainLayout';

export const TokenLogin = () => {
  const [token, setToken] = useState('');
  const [error, setError] = useState('');
  const navigate = useNavigate();
  const queryClient = useQueryClient()

  return <MainLayout>
    <div className="box-wrapper">
      <div id="login">
        {error && <div className="error">{error}</div>}
        <h1><strong>Token Login</strong></h1>
        <p>Insert your login token</p>
        <form onSubmit={(e)=>{
          e.preventDefault()
          tokenLoginRequest(token)
            .then(()=>{
              queryClient.invalidateQueries({ queryKey: ["user"] })
              navigate('/store');
            }).catch((err)=>{
              setError(err.response?.data?.message || 'An error occurred');
            })

        }}>
          <fieldset>
            <p>
              <input
                type="text"
                required
                name="token"
                placeholder="Token"
                value={token}
                onChange={(e) => setToken(e.target.value)}
              />
            </p>
            <p>
              <input type="submit" value="Invia" />
            </p>
          </fieldset>
        </form>
        <p><a href="/login">Back to 'classic' login</a></p>
        <p><a href="/register">Don't have an account?</a></p>
      </div>
    </div>
  </MainLayout>
};