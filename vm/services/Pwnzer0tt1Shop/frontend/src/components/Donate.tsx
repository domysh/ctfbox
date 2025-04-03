import { useState } from 'react';
import { donate } from '../utils/net';
import { MainLayout } from './MainLayout';
import { useQueryClient } from '@tanstack/react-query';

export const Donate = () => {
    const [amount, setAmount] = useState<string>('0');
    const [message, setMessage] = useState('');
    const [error, setError] = useState('');

    const queryClient = useQueryClient();

    return <MainLayout>
        <div className="box-wrapper">
            <div className="box">
                <img src="/imgs/coin.svg" alt="coins" />
                <h2>Donate</h2>
                <p>Donate to Pwnzer0tt1 CTF team. <br />Use the form below to donate.</p>
                <form onSubmit={(e) => {
                    e.preventDefault();
                    donate(parseFloat(amount))
                        .then(() => {
                            setMessage('Donation successful.');
                            queryClient.invalidateQueries({ queryKey: ['user']})
                        })
                        .catch((e) => {
                            setError(e.response?.data?.message || 'Si è verificato un errore durante la donazione.');
                        })
                }}>
                    <fieldset>
                        <p>
                            <input
                                type="number"
                                name="price"
                                placeholder="Inserisci la somma da donare"
                                value={amount}
                                onChange={(e) => setAmount(e.target.value)}
                                required
                            />
                        </p>
                        <p>
                            <input type="submit" value="Dona" />
                        </p>
                    </fieldset>
                </form>
                {error && <div className="error">{error}</div>}
                {message && <div className="success">{message}</div>}
            </div>
        </div>
    </MainLayout>
};
