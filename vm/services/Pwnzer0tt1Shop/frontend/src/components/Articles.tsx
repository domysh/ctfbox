import { useEffect, useState } from 'react';
import { buyArticle, useArticles } from '../utils/net';
import { MainLayout } from './MainLayout';
import { Article } from '../utils/types';
import { useQueryClient } from '@tanstack/react-query';

const SingleArticle = ({ article }:{ article: Article }) => {
  const [success, setSuccess] = useState(false)
  const [error, setError] = useState('')
  const queryClient = useQueryClient()
  const [timeoutId, setTimeoutId] = useState<number|null>(null)

  useEffect(()=>{
    if (success || error){
        if (timeoutId != null){
            window.clearTimeout(timeoutId)
        }
        setTimeoutId(setTimeout(()=>{
            setSuccess(false)
            setError('')
        }, 3000))
    }
    return ()=>{
        if (timeoutId){
            window.clearTimeout(timeoutId)
        }
    }
  }, [success, error])

  return (
      <div className="store__card">
        <div className="store__card__header">
          <img src={article.img} alt="card__image" className="card__image" width="600" />
        </div>
        <div className="store__card__body">
            {(success || error) && <div className='center-flex' style={{paddingBottom: 10}}>
                {success && <div className="success" style={{marginBottom:0}}>Item purchased successfully.</div>}
                {error && <div className="error" style={{marginBottom:0}}>{error}</div>}
            </div>}
            <div style={{display: "flex"}}>
                {!article.purchased && <span className="store__tag store__tag-red">Not Purchased</span>}
                {article.purchased && <span className="store__tag store__tag-green">Purchased</span>}
                <span className="store__tag store__tag-blue"><b>{article.price} $</b></span>
            </div>
          
          <h4>{article.title}</h4>
          <p>{article.description}</p>
          
          {article.secret && <b>Secret: {article.secret}</b>}
        </div>
        <div className="store__card__footer">
            <div className="center-flex-col" style={{ width: "100%", gap: 10}}>
                <button
                    className='store__button link-button'
                    style={article.purchased?{ cursor: 'not-allowed', opacity: 0.7 }:{}}
                    disabled={article.purchased}
                    onClick={()=>{
                        buyArticle(article.id)
                            .then(()=>{
                                setSuccess(true)
                                setError('')
                                queryClient.invalidateQueries({ queryKey: ['articles'] })
                                queryClient.invalidateQueries({ queryKey: ['user'] })
                            }).catch((err)=>{
                                setSuccess(false)
                                setError(err.response.data.message)
                            })
                    }}
                >{article.purchased? "Already purchased.": "Buy"}</button>
            </div>
        </div>
    </div>
  )
}


export const Articles = () => {

  const articles = useArticles()

  return <MainLayout>
    <div className="box-wrapper">
      <div className="auto">
        <div className="content article-list">
          {articles.isError && <div className="error">{articles.error.message}</div>}
          
          {(articles.data??[]).map((article) => <SingleArticle key={article.id} article={article} />)}
          <h3>{(articles.data??[]).length == 0?"No articles found!":null}</h3>
        </div>
      </div>
    </div>
  </MainLayout>
};