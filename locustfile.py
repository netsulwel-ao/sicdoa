"""
Locust load test for SICDOA.
Run: locust -f locustfile.py --headless -u 10 -r 2 --run-time 30s
     (assumes server at localhost:8000 with test data)
"""
from locust import HttpUser, task, between


class SICDOAUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        """Login once per user"""
        # Adjust credentials to your test environment
        resp = self.client.post("/login/", {
            "email": "adilsona87@gmail.com",
            "senha": "teste123",
        })
        if resp.status_code == 302:
            self.client.cookies.update(resp.cookies)

    @task(3)
    def lista_colaboradores(self):
        self.client.get("/rh/colaboradores/")

    @task(2)
    def lista_subsidios(self):
        self.client.get("/rh/subsidios/")

    @task(2)
    def lista_salarios(self):
        self.client.get("/rh/salarios/")

    @task(2)
    def presencas(self):
        self.client.get("/rh/presencas/")

    @task(1)
    def vagas(self):
        self.client.get("/rh/vagas/")

    @task(1)
    def dashboard(self):
        self.client.get("/rh/")
