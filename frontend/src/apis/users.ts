import { BASE_URL, makeCommonAxios, getErrMsg } from './common';
import type { User } from '../libs/users';

const API_PREFIX_PATH = "auth/login";

export interface LoginResponse {
  user?: User
  error?: string
}

const login = async (email: string, password: string): Promise<LoginResponse> => {
  return makeCommonAxios().post(
    `${BASE_URL}/${API_PREFIX_PATH}`,
    { email, password }
  )
    .then((res) => {
      return { user: res.data };
    })
    .catch((err) => {
      return { error: getErrMsg(err) }
    })
};

const API = {
  login
};

export default API;

