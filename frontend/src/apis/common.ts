import axios from 'axios';
import { get } from 'lodash';

export let BASE_URL = "http://localhost:8000";
if (!import.meta.env.DEV) {
    BASE_URL = "http://34.126.173.27:8000";
}

export const makeCommonAxios = () => {
    const ax = axios.create({
        baseURL: BASE_URL,
        withCredentials: true,
    });
    return ax;
}

export function getErrMsg(err: any): string {
    return get(err, "response.data.error", err.message);
}
