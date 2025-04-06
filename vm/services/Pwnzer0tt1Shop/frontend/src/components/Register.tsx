import { useEffect, useState } from 'react';
import { registerRequest, useUser } from '../utils/net';
import { MainLayout } from './MainLayout';
import { useNavigate } from 'react-router-dom';

export const Register = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const navigate = useNavigate()

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
            {success && <div className="success">{success}</div>}
            <h1><strong>Hi</strong> stranger!</h1>
            <form onSubmit={(e)=>{
              e.preventDefault()
              registerRequest({ username, password, email })
                .then(() => {
                  setSuccess('The account has been created correctly!')
                  setUsername('');
                  setPassword('');
                  setEmail('');
                  setError('');
                  navigate("/store")
                })
                .catch((err)=>{
                  if (err.response && err.response.data) {
                    setError(err.response.data.message || 'Something went wrong');
                  } else {
                    setError('Network error, please try again later.');
                  }
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
                <p>
                  <input
                    type="text"
                    required
                    name="email"
                    placeholder="E-mail"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                </p>
                <p><a href="/login">Do you have an account?</a></p>
                <p>
                  <input type="submit" value="Register" />
                </p>
              </fieldset>
            </form>
          </div>
        </div> 
    </MainLayout>
};

