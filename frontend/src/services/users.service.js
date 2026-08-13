import { apiGet, apiPut } from "services/api";
import { API_ENDPOINTS } from "config/api.config";

/**
 * User profile and admin user-management API helpers.
 */
export async function getMe() {
  const { data } = await apiGet(API_ENDPOINTS.USERS.ME);
  return data;
}

export async function list() {
  const { data } = await apiGet(API_ENDPOINTS.USERS.LIST);
  return data;
}

export async function getById(id) {
  const { data } = await apiGet(API_ENDPOINTS.USERS.BY_ID(id));
  return data;
}

export async function deactivate(id) {
  await apiPut(API_ENDPOINTS.USERS.DEACTIVATE(id));
}

const usersService = {
  getMe,
  list,
  getById,
  deactivate,
};

export default usersService;
