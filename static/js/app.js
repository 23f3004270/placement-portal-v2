const { createApp } = Vue;

createApp({
    data() {
        return {
            role: localStorage.getItem('role') || null,
            token: localStorage.getItem('token') || null,
            error: null,
            success: null,
            registerMode: null,
            loginForm: { email: '', password: '' },
            regForm: { name: '', email: '', password: '' },
            adminStats: null,
            companies: [],
            searchQuery: ''
        };
    },
    mounted() {
        if (this.role === 'Admin') {
            this.fetchAdminData();
        }
    },
    methods: {
        async login() {
            this.error = null;
            const res = await fetch('/api/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(this.loginForm)
            });
            const data = await res.json();
            
            if (res.ok) {
                this.token = data.token;
                this.role = data.role;
                localStorage.setItem('token', this.token);
                localStorage.setItem('role', this.role);
                this.loginForm.email = '';
                this.loginForm.password = '';
                
                if (this.role === 'Admin') {
                    this.fetchAdminData();
                }
            } else {
                this.error = data.msg;
            }
        },
        async register() {
            this.error = null;
            this.success = null;
            const endpoint = this.registerMode === 'Student' ? '/api/register/student' : '/api/register/company';
            
            const res = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(this.regForm)
            });
            const data = await res.json();

            if (res.ok) {
                this.success = "Registration successful! You can now log in.";
                this.registerMode = null;
                this.regForm = { name: '', email: '', password: '' };
            } else {
                this.error = data.msg;
            }
        },
        logout() {
            this.role = null;
            this.token = null;
            this.adminStats = null;
            this.companies = [];
            localStorage.removeItem('role');
            localStorage.removeItem('token');
        },
        async fetchAdminData() {
            const res = await fetch('/api/admin/stats', {
                headers: { 'Authorization': `Bearer ${this.token}` }
            });
            if (res.ok) {
                this.adminStats = await res.json();
                this.fetchCompanies();
            }
        },
        async fetchCompanies() {
            const res = await fetch(`/api/admin/companies?search=${this.searchQuery}`, {
                headers: { 'Authorization': `Bearer ${this.token}` }
            });
            if (res.ok) {
                this.companies = await res.json();
            }
        },
        async manageCompany(id, action) {
            const res = await fetch(`/api/admin/companies/${id}/${action}`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${this.token}` }
            });
            if (res.ok) {
                this.fetchCompanies(); 
            }
        }
    }
}).mount('#app');