import { MainLayout } from "./MainLayout"

export const NotFound = () => {
  return <MainLayout>
      <div style={{display:'flex', justifyContent:'center', alignItems:'center', paddingTop:'50px', paddingBottom:'50px'}}>
        <img src='https://http.cat/404'/>
      </div>
    </MainLayout>
};

