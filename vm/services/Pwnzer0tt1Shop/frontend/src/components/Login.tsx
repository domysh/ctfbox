import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { loginRequest, useUser } from '../utils/net';
import { useQueryClient } from '@tanstack/react-query';
import { MainLayout } from './MainLayout';

export const Login = () => {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const user = useUser()
  const hasLogin = user.data != null && !user.isError

  useEffect(()=>{
    if (user.isFetched && hasLogin){
        navigate("/store")
    }
  }, [hasLogin])

  return <MainLayout>
        <div className="box-wrapper">
          <div id="login">
            {error && <div className="error">{error}</div>}
            <h1><strong>Hi.</strong> Login with your credentials.</h1>
            <form onSubmit={(e) => {
                e.preventDefault();
                loginRequest({username, password}).then(() => {
                    queryClient.resetQueries({
                        queryKey: ['user']
                    })
                }).catch((err) => {
                    setError(err.response?.data?.message || 'An error occurred')
                })
              }}>
              <fieldset>
                <p>
                  <input
                    type="text"
                    required
                    name="user"
                    placeholder="Username"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                  />
                </p>
                <p>
                  <input
                    type="password"
                    required
                    name="psw"
                    placeholder="Password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                </p>
                <p><Link to="/register">Don't have an account?</Link></p>
                <p><Link to="/login/token">Try the NEW login with the token!</Link></p>
                <p>
                  <input type="submit" value="Login" />
                </p>
              </fieldset>
            </form>
          </div>
        </div>
    </MainLayout>
};
