/**
 * Configuração SSO - URLs de Produção
 * Centralize todas as URLs aqui
 */

const SSO_CONFIG = {
    // URLs de Produção
    PORTAL_URL: 'https://portal.cdoangola.co.ao',
    SICDOA_URL: 'https://sicdoa.netsulwel.tech',
    
    // Endpoints da API
    API: {
        VALIDATE: 'https://portal.cdoangola.co.ao/api/sso_validate.php',
        VALIDATE_TEST: 'https://portal.cdoangola.co.ao/api/sso_validate_test.php',
        LOGIN: 'https://portal.cdoangola.co.ao/api/sso_login.php',
        CALLBACK: 'https://portal.cdoangola.co.ao/sso_callback.php'
    },
    
    // Configurações
    TOKEN_EXPIRY: 15 * 60 * 1000, // 15 minutos em ms
    CHECK_INTERVAL: 2000, // 2 segundos
    TIMEOUT: 5 * 60 * 1000, // 5 minutos em ms
    
    // Popup settings (modal menor e centralizada)
    POPUP: {
        width: 300,
        height: 300,
        features: 'menubar=no,toolbar=no,location=no,scrollbars=yes,resizable=yes'
    }
};

// Exportar para uso global
window.SSO_CONFIG = SSO_CONFIG;

console.log('✅ SSO Config carregado:', SSO_CONFIG);
