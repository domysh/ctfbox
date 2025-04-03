import { BrowserRouter as Router, Routes, Route, useNavigate } from 'react-router-dom';
import { Home } from './components/Home';
import { Articles } from './components/Articles';
import { Donate } from './components/Donate';
import Sell from './components/Sell';
import { Login } from './components/Login';
import { Register } from './components/Register';
import { TokenLogin } from './components/TokenLogin';
import { NotFound } from './components/NotFound';
import { useEffect } from 'react';
import { useUser } from './utils/net';
import { Profile } from './components/Profile';

export const App = () => {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/login/token" element={<TokenLogin />} />
        <Route path="*" element={<ProtectedApp />} />
      </Routes>
    </Router>
  );
};


export const ProtectedApp = () => {

  const user = useUser()
  const navigate = useNavigate()

  useEffect(()=>{
    if (user.error){
      navigate("/login")
    }

  },[user.isFetching])

  return <Routes>
    <Route path="/store" element={<Articles />} />
    <Route path="/donate" element={<Donate />} />
    <Route path="/sell" element={<Sell />} />
    <Route path="/profile" element={<Profile />} />
    <Route path="*" element={<NotFound />} />
  </Routes>

}