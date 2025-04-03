import { useState } from 'react';
import { sellArticle } from '../utils/net';
import { MainLayout } from './MainLayout';
import { useNavigate } from 'react-router-dom';

export const Sell = () => {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [price, setPrice] = useState('');
  const [secret, setSecret] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const navigate = useNavigate();

  return <MainLayout>
    <div className="box-wrapper">
      <div className="box">
        <h2>Sell an Article</h2>
        <p>Compile the module to sell an article</p>
        <form onSubmit={(e)=>{
          e.preventDefault()
          sellArticle({ title, description, price:parseFloat(price), secret })
            .then((response)=>{
              setMessage(response.message);
              setTitle('');
              setDescription('');
              setPrice('');
              navigate('/store');
            }).catch((err)=>{
              setError(err.response.message);
            })
        }}>
          <fieldset>
            <p>
              <input 
                type="text" 
                placeholder="Title" 
                value={title} 
                onChange={(e) => setTitle(e.target.value)} 
                required 
              />
            </p>
            <p>
              <input 
                type="text" 
                placeholder="Description" 
                value={description} 
                onChange={(e) => setDescription(e.target.value)} 
                required 
              />
            </p>
            <p>
              <input 
                type="number" 
                placeholder="Price" 
                value={price} 
                onChange={(e) => setPrice(e.target.value)} 
                required 
              />
            </p>
            <p>
              <input 
                type="text" 
                placeholder="Secret Content"
                value={secret} 
                onChange={(e) => setSecret(e.target.value)} 
                required 
              />
            </p>
            <p>
              <input type="submit" value="Sell" />
            </p>
          </fieldset>
        </form>
        {message && <div className="success">{message}</div>}
        {error && <div className="error">{error}</div>}
      </div>
    </div>
    </MainLayout>
};

export default Sell;
