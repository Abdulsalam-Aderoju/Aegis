const API_BASE = "https://aegis-backend.redstone-d9d0cf4c.southafricanorth.azurecontainerapps.io/";


const Auth = {
    // Store token and user info after login
    save(data) {
        localStorage.setItem("aegis_token", data.access_token);
        localStorage.setItem("aegis_role", data.role);
        localStorage.setItem("aegis_state", data.state || "");
        localStorage.setItem("aegis_name", data.operator_name);
    },

    // Get the stored token
    getToken() {
        return localStorage.getItem("aegis_token");
    },

    // Get user info
    getUser() {
        return {
            name: localStorage.getItem("aegis_name"),
            role: localStorage.getItem("aegis_role"),
            state: localStorage.getItem("aegis_state"),
        };
    },

    // Check if logged in
    isLoggedIn() {
        return !!this.getToken();
    },

    // Clear everything on logout
    logout() {
        localStorage.removeItem("aegis_token");
        localStorage.removeItem("aegis_role");
        localStorage.removeItem("aegis_state");
        localStorage.removeItem("aegis_name");
        window.location.href = "login.html";
    },

    // Authenticated fetch wrapper — auto-attaches JWT header
    async fetch(endpoint, options = {}) {
        const token = this.getToken();
        if (!token) {
            window.location.href = "login.html";
            return;
        }

        const headers = {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
            ...(options.headers || {}),
        };

        const response = await fetch(`${API_BASE}${endpoint}`, {
            ...options,
            headers,
        });

        // If 401, token expired, redirect to login
        if (response.status === 401) {
            this.logout();
            return;
        }

        return response;
    },

    // Redirect if not authenticated or wrong role
    requireRole(role) {
        if (!this.isLoggedIn()) {
            window.location.href = "login.html";
            return false;
        }
        if (this.getUser().role !== role) {
            window.location.href = "login.html";
            return false;
        }
        return true;
    },

    // Get initials for avatar
    getInitials() {
        const state = this.getUser().state || "??";
        return state.substring(0, 2).toUpperCase();
    },
};
