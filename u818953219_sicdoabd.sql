-- phpMyAdmin SQL Dump
-- version 5.2.2
-- https://www.phpmyadmin.net/
--
-- Host: 127.0.0.1:3306
-- Tempo de geração: 12-Jun-2026 às 16:34
-- Versão do servidor: 11.8.6-MariaDB-log
-- versão do PHP: 7.2.34

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- Base de dados: `u818953219_sicdoabd`
--

-- --------------------------------------------------------

--
-- Estrutura da tabela `auth_group`
--

CREATE TABLE `auth_group` (
  `id` int(11) NOT NULL,
  `name` varchar(150) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `auth_group_permissions`
--

CREATE TABLE `auth_group_permissions` (
  `id` bigint(20) NOT NULL,
  `group_id` int(11) NOT NULL,
  `permission_id` int(11) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `auth_permission`
--

CREATE TABLE `auth_permission` (
  `id` int(11) NOT NULL,
  `name` varchar(255) NOT NULL,
  `content_type_id` int(11) NOT NULL,
  `codename` varchar(100) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

--
-- Extraindo dados da tabela `auth_permission`
--

INSERT INTO `auth_permission` (`id`, `name`, `content_type_id`, `codename`) VALUES
(1, 'Can add log entry', 1, 'add_logentry'),
(2, 'Can change log entry', 1, 'change_logentry'),
(3, 'Can delete log entry', 1, 'delete_logentry'),
(4, 'Can view log entry', 1, 'view_logentry'),
(5, 'Can add permission', 2, 'add_permission'),
(6, 'Can change permission', 2, 'change_permission'),
(7, 'Can delete permission', 2, 'delete_permission'),
(8, 'Can view permission', 2, 'view_permission'),
(9, 'Can add group', 3, 'add_group'),
(10, 'Can change group', 3, 'change_group'),
(11, 'Can delete group', 3, 'delete_group'),
(12, 'Can view group', 3, 'view_group'),
(13, 'Can add user', 4, 'add_user'),
(14, 'Can change user', 4, 'change_user'),
(15, 'Can delete user', 4, 'delete_user'),
(16, 'Can view user', 4, 'view_user'),
(17, 'Can add content type', 5, 'add_contenttype'),
(18, 'Can change content type', 5, 'change_contenttype'),
(19, 'Can delete content type', 5, 'delete_contenttype'),
(20, 'Can view content type', 5, 'view_contenttype'),
(21, 'Can add Utilizador', 6, 'add_usuario'),
(22, 'Can change Utilizador', 6, 'change_usuario'),
(23, 'Can delete Utilizador', 6, 'delete_usuario'),
(24, 'Can view Utilizador', 6, 'view_usuario'),
(25, 'Can add Declaração Única', 7, 'add_declaracaounica'),
(26, 'Can change Declaração Única', 7, 'change_declaracaounica'),
(27, 'Can delete Declaração Única', 7, 'delete_declaracaounica'),
(28, 'Can view Declaração Única', 7, 'view_declaracaounica'),
(29, 'Can add Assembleia', 8, 'add_assembleia'),
(30, 'Can change Assembleia', 8, 'change_assembleia'),
(31, 'Can delete Assembleia', 8, 'delete_assembleia'),
(32, 'Can view Assembleia', 8, 'view_assembleia'),
(33, 'Can add Ata Digital', 9, 'add_atadigital'),
(34, 'Can change Ata Digital', 9, 'change_atadigital'),
(35, 'Can delete Ata Digital', 9, 'delete_atadigital'),
(36, 'Can view Ata Digital', 9, 'view_atadigital'),
(37, 'Can add Manifesto de Integridade', 10, 'add_manifestointegridade'),
(38, 'Can change Manifesto de Integridade', 10, 'change_manifestointegridade'),
(39, 'Can delete Manifesto de Integridade', 10, 'delete_manifestointegridade'),
(40, 'Can view Manifesto de Integridade', 10, 'view_manifestointegridade'),
(41, 'Can add Notificação', 11, 'add_notificacao'),
(42, 'Can change Notificação', 11, 'change_notificacao'),
(43, 'Can delete Notificação', 11, 'delete_notificacao'),
(44, 'Can view Notificação', 11, 'view_notificacao'),
(45, 'Can add Pauta de Votação', 12, 'add_pautavotacao'),
(46, 'Can change Pauta de Votação', 12, 'change_pautavotacao'),
(47, 'Can delete Pauta de Votação', 12, 'delete_pautavotacao'),
(48, 'Can view Pauta de Votação', 12, 'view_pautavotacao'),
(49, 'Can add Presença', 13, 'add_presencaassembleia'),
(50, 'Can change Presença', 13, 'change_presencaassembleia'),
(51, 'Can delete Presença', 13, 'delete_presencaassembleia'),
(52, 'Can view Presença', 13, 'view_presencaassembleia'),
(53, 'Can add Procuração', 14, 'add_procuracao'),
(54, 'Can change Procuração', 14, 'change_procuracao'),
(55, 'Can delete Procuração', 14, 'delete_procuracao'),
(56, 'Can view Procuração', 14, 'view_procuracao'),
(57, 'Can add Voto', 15, 'add_voto'),
(58, 'Can change Voto', 15, 'change_voto'),
(59, 'Can delete Voto', 15, 'delete_voto'),
(60, 'Can view Voto', 15, 'view_voto'),
(61, 'Can add Recibo de Voto', 16, 'add_recibovoto'),
(62, 'Can change Recibo de Voto', 16, 'change_recibovoto'),
(63, 'Can delete Recibo de Voto', 16, 'delete_recibovoto'),
(64, 'Can view Recibo de Voto', 16, 'view_recibovoto'),
(65, 'Can add Documento', 17, 'add_documentoassembleia'),
(66, 'Can change Documento', 17, 'change_documentoassembleia'),
(67, 'Can delete Documento', 17, 'delete_documentoassembleia'),
(68, 'Can view Documento', 17, 'view_documentoassembleia'),
(69, 'Can add Membro da Mesa', 18, 'add_membromesa'),
(70, 'Can change Membro da Mesa', 18, 'change_membromesa'),
(71, 'Can delete Membro da Mesa', 18, 'delete_membromesa'),
(72, 'Can view Membro da Mesa', 18, 'view_membromesa'),
(73, 'Can add Mensagem de Chat', 19, 'add_mensagemchat'),
(74, 'Can change Mensagem de Chat', 19, 'change_mensagemchat'),
(75, 'Can delete Mensagem de Chat', 19, 'delete_mensagemchat'),
(76, 'Can view Mensagem de Chat', 19, 'view_mensagemchat'),
(77, 'Can add Carteira Profissional', 20, 'add_carteiraprofissional'),
(78, 'Can change Carteira Profissional', 20, 'change_carteiraprofissional'),
(79, 'Can delete Carteira Profissional', 20, 'delete_carteiraprofissional'),
(80, 'Can view Carteira Profissional', 20, 'view_carteiraprofissional'),
(81, 'Can add Certidão de Regularidade', 21, 'add_certidaoregularidade'),
(82, 'Can change Certidão de Regularidade', 21, 'change_certidaoregularidade'),
(83, 'Can delete Certidão de Regularidade', 21, 'delete_certidaoregularidade'),
(84, 'Can view Certidão de Regularidade', 21, 'view_certidaoregularidade'),
(85, 'Can add Estado Financeiro', 22, 'add_estadofinanceiro'),
(86, 'Can change Estado Financeiro', 22, 'change_estadofinanceiro'),
(87, 'Can delete Estado Financeiro', 22, 'delete_estadofinanceiro'),
(88, 'Can view Estado Financeiro', 22, 'view_estadofinanceiro'),
(89, 'Can add Configuração de Quota', 23, 'add_quotaconfig'),
(90, 'Can change Configuração de Quota', 23, 'change_quotaconfig'),
(91, 'Can delete Configuração de Quota', 23, 'delete_quotaconfig'),
(92, 'Can view Configuração de Quota', 23, 'view_quotaconfig'),
(93, 'Can add Quota Gerada', 24, 'add_quotagerada'),
(94, 'Can change Quota Gerada', 24, 'change_quotagerada'),
(95, 'Can delete Quota Gerada', 24, 'delete_quotagerada'),
(96, 'Can view Quota Gerada', 24, 'view_quotagerada'),
(97, 'Can add Pagamento de Quota', 25, 'add_pagamentoquota'),
(98, 'Can change Pagamento de Quota', 25, 'change_pagamentoquota'),
(99, 'Can delete Pagamento de Quota', 25, 'delete_pagamentoquota'),
(100, 'Can view Pagamento de Quota', 25, 'view_pagamentoquota'),
(101, 'Can add Artigo do Documento', 26, 'add_artigodocumento'),
(102, 'Can change Artigo do Documento', 26, 'change_artigodocumento'),
(103, 'Can delete Artigo do Documento', 26, 'delete_artigodocumento'),
(104, 'Can view Artigo do Documento', 26, 'view_artigodocumento'),
(105, 'Can add Comentário', 27, 'add_comentario'),
(106, 'Can change Comentário', 27, 'change_comentario'),
(107, 'Can delete Comentário', 27, 'delete_comentario'),
(108, 'Can view Comentário', 27, 'view_comentario'),
(109, 'Can add Consulta Pública', 28, 'add_consultapublica'),
(110, 'Can change Consulta Pública', 28, 'change_consultapublica'),
(111, 'Can delete Consulta Pública', 28, 'delete_consultapublica'),
(112, 'Can view Consulta Pública', 28, 'view_consultapublica'),
(113, 'Can add Relatório de Consulta', 29, 'add_relatorioconsulta'),
(114, 'Can change Relatório de Consulta', 29, 'change_relatorioconsulta'),
(115, 'Can delete Relatório de Consulta', 29, 'delete_relatorioconsulta'),
(116, 'Can view Relatório de Consulta', 29, 'view_relatorioconsulta'),
(117, 'Can add Votação de Consulta', 30, 'add_votacaoconsulta'),
(118, 'Can change Votação de Consulta', 30, 'change_votacaoconsulta'),
(119, 'Can delete Votação de Consulta', 30, 'delete_votacaoconsulta'),
(120, 'Can view Votação de Consulta', 30, 'view_votacaoconsulta'),
(121, 'Can add Voto em Consulta', 31, 'add_votoconsulta'),
(122, 'Can change Voto em Consulta', 31, 'change_votoconsulta'),
(123, 'Can delete Voto em Consulta', 31, 'delete_votoconsulta'),
(124, 'Can view Voto em Consulta', 31, 'view_votoconsulta'),
(125, 'Can add Convocatória', 32, 'add_convocatoria'),
(126, 'Can change Convocatória', 32, 'change_convocatoria'),
(127, 'Can delete Convocatória', 32, 'delete_convocatoria'),
(128, 'Can view Convocatória', 32, 'view_convocatoria'),
(129, 'Can add Log da Assembleia', 33, 'add_logassembleia'),
(130, 'Can change Log da Assembleia', 33, 'change_logassembleia'),
(131, 'Can delete Log da Assembleia', 33, 'delete_logassembleia'),
(132, 'Can view Log da Assembleia', 33, 'view_logassembleia'),
(133, 'Can add Resposta de Presença', 34, 'add_respostapresenca'),
(134, 'Can change Resposta de Presença', 34, 'change_respostapresenca'),
(135, 'Can delete Resposta de Presença', 34, 'delete_respostapresenca'),
(136, 'Can view Resposta de Presença', 34, 'view_respostapresenca'),
(137, 'Can add Categoria de Membro', 35, 'add_categoriamembro'),
(138, 'Can change Categoria de Membro', 35, 'change_categoriamembro'),
(139, 'Can delete Categoria de Membro', 35, 'delete_categoriamembro'),
(140, 'Can view Categoria de Membro', 35, 'view_categoriamembro'),
(141, 'Can add Isenção de Membro', 36, 'add_isencaomembro'),
(142, 'Can change Isenção de Membro', 36, 'change_isencaomembro'),
(143, 'Can delete Isenção de Membro', 36, 'delete_isencaomembro'),
(144, 'Can view Isenção de Membro', 36, 'view_isencaomembro'),
(145, 'Can add Tipo de Quota', 37, 'add_tipoquota'),
(146, 'Can change Tipo de Quota', 37, 'change_tipoquota'),
(147, 'Can delete Tipo de Quota', 37, 'delete_tipoquota'),
(148, 'Can view Tipo de Quota', 37, 'view_tipoquota'),
(149, 'Can add Histórico de Quota', 38, 'add_historicoquota'),
(150, 'Can change Histórico de Quota', 38, 'change_historicoquota'),
(151, 'Can delete Histórico de Quota', 38, 'delete_historicoquota'),
(152, 'Can view Histórico de Quota', 38, 'view_historicoquota');

-- --------------------------------------------------------

--
-- Estrutura da tabela `auth_user`
--

CREATE TABLE `auth_user` (
  `id` int(11) NOT NULL,
  `password` varchar(128) NOT NULL,
  `last_login` datetime(6) DEFAULT NULL,
  `is_superuser` tinyint(1) NOT NULL,
  `username` varchar(150) NOT NULL,
  `first_name` varchar(150) NOT NULL,
  `last_name` varchar(150) NOT NULL,
  `email` varchar(254) NOT NULL,
  `is_staff` tinyint(1) NOT NULL,
  `is_active` tinyint(1) NOT NULL,
  `date_joined` datetime(6) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `auth_user_groups`
--

CREATE TABLE `auth_user_groups` (
  `id` bigint(20) NOT NULL,
  `user_id` int(11) NOT NULL,
  `group_id` int(11) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `auth_user_user_permissions`
--

CREATE TABLE `auth_user_user_permissions` (
  `id` bigint(20) NOT NULL,
  `user_id` int(11) NOT NULL,
  `permission_id` int(11) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `cargos`
--

CREATE TABLE `cargos` (
  `id` bigint(20) NOT NULL,
  `nome` varchar(100) NOT NULL,
  `slug` varchar(100) NOT NULL,
  `descricao` longtext NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `sistema` tinyint(1) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

--
-- Extraindo dados da tabela `cargos`
--

INSERT INTO `cargos` (`id`, `nome`, `slug`, `descricao`, `created_at`, `sistema`) VALUES
(1, 'Recursos Humanos', 'recursos-humanos', 'O Usuario com esse nivel de acesso pode fazer a gestão de RH dos despachnates.', '2026-06-09 08:50:31.270942', 0);

-- --------------------------------------------------------

--
-- Estrutura da tabela `cargos_permissoes`
--

CREATE TABLE `cargos_permissoes` (
  `id` bigint(20) NOT NULL,
  `cargo_id` bigint(20) NOT NULL,
  `permissao_id` bigint(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `clientes_clientes`
--

CREATE TABLE `clientes_clientes` (
  `id` bigint(20) NOT NULL,
  `nome` varchar(255) NOT NULL,
  `nif` varchar(50) NOT NULL,
  `localizacao` longtext NOT NULL,
  `telefone` varchar(30) NOT NULL,
  `email` varchar(254) NOT NULL,
  `observacoes` longtext NOT NULL,
  `ativo` tinyint(1) NOT NULL,
  `criado_em` datetime(6) NOT NULL,
  `atualizado_em` datetime(6) NOT NULL,
  `usuario_id` int(11) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

--
-- Extraindo dados da tabela `clientes_clientes`
--

INSERT INTO `clientes_clientes` (`id`, `nome`, `nif`, `localizacao`, `telefone`, `email`, `observacoes`, `ativo`, `criado_em`, `atualizado_em`, `usuario_id`) VALUES
(1, 'ESTEVÃO MATEUS SUPULETA ANTÓNIO', '000821963HA034', 'PRIMEIRO DE MAIO', '925666034', '', '', 1, '2026-06-12 08:45:41.932930', '2026-06-12 08:45:41.932990', 5),
(2, 'ANGATA', '5417355267', 'LOBITO', '', '', '', 1, '2026-06-12 08:51:19.178591', '2026-06-12 09:16:30.482836', 5),
(3, 'POPULAR HJUICE INDUSTRIES- PRODUÇÃO DE SUMOS, LDA', '5417545600', 'POLO INDUSTRIAL DA CATUMBELA', '92416096', '', '', 1, '2026-06-12 09:05:06.479517', '2026-06-12 09:31:06.440691', 5),
(4, 'Adilson Pedro António Abel', '22444722', 'Huila', '900000000', 'adilsonao87@gmail.com', '', 1, '2026-06-12 09:28:38.283563', '2026-06-12 09:28:38.283599', 4);

-- --------------------------------------------------------

--
-- Estrutura da tabela `declaracoes_unicas`
--

CREATE TABLE `declaracoes_unicas` (
  `id` bigint(20) NOT NULL,
  `numero_du` varchar(50) DEFAULT NULL,
  `processo_id` int(11) DEFAULT NULL,
  `nif_declarante` varchar(50) NOT NULL,
  `nome_declarante` varchar(200) NOT NULL,
  `endereco_declarante` longtext DEFAULT NULL,
  `regime_aduaneiro` varchar(100) NOT NULL,
  `codigo_pautal` varchar(20) NOT NULL,
  `descricao_mercadoria` longtext DEFAULT NULL,
  `quantidade` int(11) NOT NULL,
  `peso_bruto` decimal(10,2) NOT NULL,
  `peso_liquido` decimal(10,2) NOT NULL,
  `valor_fob` decimal(15,2) NOT NULL,
  `valor_frete` decimal(15,2) DEFAULT NULL,
  `valor_seguro` decimal(15,2) DEFAULT NULL,
  `valor_cif` decimal(15,2) NOT NULL,
  `direitos_aduaneiros` decimal(15,2) DEFAULT NULL,
  `iva` decimal(15,2) DEFAULT NULL,
  `imposto_consumo` decimal(15,2) DEFAULT NULL,
  `emolumentos` decimal(15,2) DEFAULT NULL,
  `total_impostos` decimal(15,2) DEFAULT NULL,
  `pais_origem` varchar(100) DEFAULT NULL,
  `porto_embarque` varchar(100) DEFAULT NULL,
  `porto_desembarque` varchar(100) DEFAULT NULL,
  `meio_transporte` varchar(50) DEFAULT NULL,
  `status` varchar(20) NOT NULL,
  `data_submissao` datetime(6) DEFAULT NULL,
  `data_aprovacao` datetime(6) DEFAULT NULL,
  `usuario_id` int(11) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `du_uuid` varchar(36) NOT NULL,
  `codigo_processo` varchar(8) DEFAULT NULL,
  `ref_despachante` varchar(100) NOT NULL,
  `exportador_nome` varchar(200) NOT NULL,
  `destinatario_nome` varchar(200) NOT NULL,
  `total_derimp` decimal(18,2) NOT NULL,
  `total_iec` decimal(18,2) NOT NULL,
  `total_emgead` decimal(18,2) NOT NULL,
  `total_direxp` decimal(18,2) NOT NULL,
  `total_iva` decimal(18,2) NOT NULL,
  `total_geral` decimal(18,2) NOT NULL,
  `dados_json` longtext NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

--
-- Extraindo dados da tabela `declaracoes_unicas`
--

INSERT INTO `declaracoes_unicas` (`id`, `numero_du`, `processo_id`, `nif_declarante`, `nome_declarante`, `endereco_declarante`, `regime_aduaneiro`, `codigo_pautal`, `descricao_mercadoria`, `quantidade`, `peso_bruto`, `peso_liquido`, `valor_fob`, `valor_frete`, `valor_seguro`, `valor_cif`, `direitos_aduaneiros`, `iva`, `imposto_consumo`, `emolumentos`, `total_impostos`, `pais_origem`, `porto_embarque`, `porto_desembarque`, `meio_transporte`, `status`, `data_submissao`, `data_aprovacao`, `usuario_id`, `created_at`, `updated_at`, `du_uuid`, `codigo_processo`, `ref_despachante`, `exportador_nome`, `destinatario_nome`, `total_derimp`, `total_iec`, `total_emgead`, `total_direxp`, `total_iva`, `total_geral`, `dados_json`) VALUES
(1, NULL, NULL, '', '', NULL, 'IM4', '', '', 0, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, NULL, NULL, NULL, NULL, 'Rascunho', NULL, NULL, 5, '2026-06-10 08:47:00.667649', '2026-06-10 09:02:59.242323', '156a02a7-6f4d-4270-a625-ec8728483b0a', '93331179', 'LDA12_26', '', '', 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, '{\"csrfmiddlewaretoken\": \"ivUhMfY3E0zY9iUh9aqJGtMFe3jrGmvgKyFq7IuBVSl5afJSoYNqcoV2GrhKyEJG\", \"estancia\": \"4POLB\", \"regime_aduaneiro\": \"IM4\", \"ref_despachante\": \"LDA12_26\", \"vinheta\": \"\", \"exportador_codigo\": \"\", \"exportador_nome\": \"\", \"exportador_endereco\": \"\", \"destinatario_nif\": \"\", \"destinatario_nome\": \"\", \"destinatario_telefone\": \"\", \"destinatario_endereco\": \"\", \"conta_credito\": \"\", \"conta_garantias\": \"\", \"localizacao_mercadoria\": \"\", \"identificacao_armzem\": \"\", \"incoterm\": \"\", \"natureza_transacao\": \"\", \"valor_fob\": \"\", \"moeda_fob\": \"AOA\", \"cambio_fob\": \"\", \"valor_fob_kz\": \"\", \"valor_seguro\": \"\", \"reparticao_seguro\": \"sem_reparticao\", \"moeda_seguro\": \"AOA\", \"cambio_seguro\": \"\", \"valor_seguro_kz\": \"\", \"valor_frete\": \"\", \"reparticao_frete\": \"sem_reparticao\", \"moeda_frete\": \"AOA\", \"cambio_frete\": \"\", \"valor_frete_kz\": \"\", \"montante_aduaneiro_kz\": \"\", \"modo_transporte_fronteira\": \"\", \"modo_transporte_interior\": \"\", \"transporte_identidade\": \"\", \"transporte_nacionalidade\": \"\", \"container\": \"0\", \"estancia_destino\": \"\", \"pais_destino_campo53\": \"\", \"local_campo54\": \"Luanda, Angola\", \"data_campo54\": \"2026-06-10\", \"forma_pagamento\": \"\", \"num_liquidacao\": \"\", \"num_recibo\": \"\", \"adicoes\": []}'),
(2, NULL, NULL, 'POPULAR JUICE IND.(PVT.) LTD.', '', NULL, 'IM4', '', '', 0, 0.00, 0.00, 105845758.30, 6225000.00, 20750.00, 112091508.30, 2241830.17, 15446118.61, 0.00, 2241830.17, 19929778.95, NULL, NULL, NULL, NULL, 'Rascunho', NULL, NULL, 5, '2026-06-12 08:39:05.316539', '2026-06-12 09:40:06.640651', 'cc8bdd24-dfcd-4dda-b0b7-ca9a32e893ad', '48315633', 'LDA061_26', '', 'POPULAR HJUICE INDUSTRIES- PRODUÇÃO DE SUMOS, LDA', 2241830.17, 0.00, 2241830.17, 0.00, 15446118.61, 19929778.95, '{\"csrfmiddlewaretoken\": \"s8jdYVVuzNz8T67C43HVHEinlAI0dZptVa3sDffrozJCQwfomRXi59BRDXRl1t1I\", \"estancia\": \"3POLA\", \"regime_aduaneiro\": \"IM4\", \"ref_despachante\": \"LDA061_26\", \"vinheta\": \"\", \"exportador_codigo\": \"POPULAR JUICE IND.(PVT.) LTD.\", \"exportador_nome\": \"\", \"exportador_endereco\": \"JAM SHORO THANA BOLA KHAN SINDH\", \"destinatario_nif\": \"5417545600\", \"destinatario_nome\": \"POPULAR HJUICE INDUSTRIES- PRODUÇÃO DE SUMOS, LDA\", \"destinatario_telefone\": \"92416096\", \"destinatario_endereco\": \"POLO INDUSTRIAL DA CATUMBELA\", \"conta_credito\": \"\", \"conta_garantias\": \"\", \"localizacao_mercadoria\": \"\", \"identificacao_armzem\": \"\", \"incoterm\": \"CIF\", \"natureza_transacao\": \"1\", \"valor_fob\": \"127525.01\", \"moeda_fob\": \"USD\", \"cambio_fob\": \"830.0000\", \"valor_fob_kz\": \"105845758.30\", \"valor_seguro\": \"25\", \"reparticao_seguro\": \"sem_reparticao\", \"moeda_seguro\": \"USD\", \"cambio_seguro\": \"830.0000\", \"valor_seguro_kz\": \"20750.00\", \"valor_frete\": \"7500\", \"reparticao_frete\": \"sem_reparticao\", \"moeda_frete\": \"USD\", \"cambio_frete\": \"830.0000\", \"valor_frete_kz\": \"6225000.00\", \"montante_aduaneiro_kz\": \"112091508.30\", \"modo_transporte_fronteira\": \"1\", \"modo_transporte_interior\": \"\", \"transporte_identidade\": \"NAVIO API BHUM\", \"transporte_nacionalidade\": \"\", \"container\": \"1\", \"container_numero[]\": \"HAMU\", \"container_num_pacotes[]\": \"\", \"container_tipo[]\": \"40HC\", \"container_ef[]\": \"F\", \"container_peso_vazio[]\": \"\", \"container_peso_mercadorias[]\": \"27975\", \"container_mercadorias[]\": \"CARTÕES\", \"container_adicoes[]\": \"[]\", \"estancia_destino\": \"LUANDA\", \"pais_destino_campo53\": \"\", \"local_campo54\": \"Luanda, Angola\", \"data_campo54\": \"2026-06-12\", \"forma_pagamento\": \"\", \"num_liquidacao\": \"\", \"num_recibo\": \"\", \"adicoes\": [{\"num_adicao\": \"1\", \"pais_origem\": \"KE\", \"codigo_pautal\": \"48115900\", \"descricao_mercadoria\": \"CARTÕES\", \"numero_volume\": \"384\", \"tipo_volume\": \"PK\", \"peso_bruto\": \"55950\", \"peso_liquido\": \"54824\", \"quantidade\": \"\", \"unidade\": \"\", \"preferencia\": \"\", \"codigo_procedimento\": \"4000\", \"codigo_isencao\": \"000\", \"quota\": \"\", \"documento_precedente\": \"HLCUKHI260307208\", \"valor_fob\": \"127525.01\", \"moeda_fob\": \"USD\", \"cambio_fob\": \"830.0000\", \"valor_fob_kz\": \"105845758.30\", \"valor_seguro\": \"25\", \"moeda_seguro\": \"USD\", \"cambio_seguro\": \"830.0000\", \"valor_seguro_kz\": \"20750.00\", \"valor_frete\": \"7500\", \"moeda_frete\": \"USD\", \"cambio_frete\": \"830.0000\", \"valor_frete_kz\": \"6225000.00\", \"montante_kz\": \"112091508.30\", \"impostos\": {\"DERIMP\": {\"valor\": 2241830.1659999997, \"taxa\": 2.0, \"base\": 112091508.3, \"acao\": \"DoTax\", \"credito\": \"1\"}, \"IEC\": {\"valor\": 0.0, \"taxa\": 0.0, \"base\": 112091508.3, \"acao\": \"DoTax\", \"credito\": \"1\"}, \"EMGEAD\": {\"valor\": 2241830.1659999997, \"taxa\": 2.0, \"base\": 112091508.3, \"acao\": \"DoTax\", \"credito\": \"1\"}, \"DIREXP\": {\"valor\": 0.0, \"taxa\": 0.0, \"base\": 0.0, \"acao\": \"N/A\", \"credito\": \"0\"}, \"IVA\": {\"valor\": 15446118.608479999, \"taxa\": 14.0, \"base\": 110329418.63199998, \"acao\": \"DoTax\", \"credito\": \"1\"}}}]}'),
(3, NULL, NULL, '5417355267', 'ANGATA', NULL, 'IM4', '', '', 0, 0.00, 0.00, 179902325.70, 27455570.00, 517729.10, 207875624.80, 0.00, 0.00, 0.00, 0.00, 0.00, NULL, NULL, NULL, NULL, 'Rascunho', NULL, NULL, 5, '2026-06-12 09:27:17.691106', '2026-06-12 09:43:06.671829', '05dc2910-c582-4a46-a894-5cc71dc109df', '69034639', 'REF-2026033', 'ANGATA', '', 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, '{\"csrfmiddlewaretoken\": \"MR5YAaQ7q8xt5PLqPHNtqt90NrzHp0fEeUQ7VDmFH0jA6MA14vaaWoinfPx0hit4\", \"estancia\": \"4POLB\", \"regime_aduaneiro\": \"IM4\", \"ref_despachante\": \"REF-2026033\", \"vinheta\": \"\", \"exportador_codigo\": \"5417355267\", \"exportador_nome\": \"ANGATA\", \"exportador_endereco\": \"LOBITO\", \"destinatario_nif\": \"5417355267\", \"destinatario_nome\": \"\", \"destinatario_telefone\": \"\", \"destinatario_endereco\": \"\", \"conta_credito\": \"120000\", \"conta_garantias\": \"500000\", \"localizacao_mercadoria\": \"\", \"identificacao_armzem\": \"\", \"incoterm\": \"CIF\", \"natureza_transacao\": \"1\", \"valor_fob\": \"216749.79\", \"moeda_fob\": \"USD\", \"cambio_fob\": \"830.0000\", \"valor_fob_kz\": \"179902325.70\", \"valor_seguro\": \"623.77\", \"reparticao_seguro\": \"valor\", \"moeda_seguro\": \"USD\", \"cambio_seguro\": \"830.0000\", \"valor_seguro_kz\": \"517729.10\", \"valor_frete\": \"33079\", \"reparticao_frete\": \"valor\", \"moeda_frete\": \"USD\", \"cambio_frete\": \"830.0000\", \"valor_frete_kz\": \"27455570.00\", \"montante_aduaneiro_kz\": \"207875624.80\", \"modo_transporte_fronteira\": \"\", \"modo_transporte_interior\": \"\", \"transporte_identidade\": \"\", \"transporte_nacionalidade\": \"\", \"container\": \"0\", \"estancia_destino\": \"\", \"pais_destino_campo53\": \"\", \"local_campo54\": \"Luanda, Angola\", \"data_campo54\": \"2026-06-12\", \"forma_pagamento\": \"\", \"num_liquidacao\": \"\", \"num_recibo\": \"\", \"adicoes\": [{\"num_adicao\": \"1\", \"pais_origem\": \"\", \"codigo_pautal\": \"31052000\", \"descricao_mercadoria\": \"NP 03 46\", \"numero_volume\": \"480\", \"tipo_volume\": \"SA\", \"peso_bruto\": \"473200\", \"peso_liquido\": \"\", \"quantidade\": \"\", \"unidade\": \"\", \"preferencia\": \"\", \"codigo_procedimento\": \"\", \"codigo_isencao\": \"000\", \"quota\": \"\", \"documento_precedente\": \"\", \"valor_fob\": \"0\", \"moeda_fob\": \"AOA\", \"cambio_fob\": \"\", \"valor_fob_kz\": \"0\", \"valor_seguro\": \"0\", \"moeda_seguro\": \"AOA\", \"cambio_seguro\": \"\", \"valor_seguro_kz\": \"0\", \"valor_frete\": \"0\", \"moeda_frete\": \"AOA\", \"cambio_frete\": \"\", \"valor_frete_kz\": \"0\", \"montante_kz\": \"0\"}]}');

-- --------------------------------------------------------

--
-- Estrutura da tabela `django_admin_log`
--

CREATE TABLE `django_admin_log` (
  `id` int(11) NOT NULL,
  `action_time` datetime(6) NOT NULL,
  `object_id` longtext DEFAULT NULL,
  `object_repr` varchar(200) NOT NULL,
  `action_flag` smallint(5) UNSIGNED NOT NULL,
  `change_message` longtext NOT NULL,
  `content_type_id` int(11) DEFAULT NULL,
  `user_id` int(11) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `django_apscheduler_djangojob`
--

CREATE TABLE `django_apscheduler_djangojob` (
  `id` varchar(255) NOT NULL,
  `next_run_time` datetime(6) DEFAULT NULL,
  `job_state` longblob NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `django_apscheduler_djangojobexecution`
--

CREATE TABLE `django_apscheduler_djangojobexecution` (
  `id` bigint(20) NOT NULL,
  `status` varchar(50) NOT NULL,
  `run_time` datetime(6) NOT NULL,
  `duration` decimal(15,2) DEFAULT NULL,
  `finished` decimal(15,2) DEFAULT NULL,
  `exception` varchar(1000) DEFAULT NULL,
  `traceback` longtext DEFAULT NULL,
  `job_id` varchar(255) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `django_content_type`
--

CREATE TABLE `django_content_type` (
  `id` int(11) NOT NULL,
  `app_label` varchar(100) NOT NULL,
  `model` varchar(100) NOT NULL,
  `name` varchar(50) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

--
-- Extraindo dados da tabela `django_content_type`
--

INSERT INTO `django_content_type` (`id`, `app_label`, `model`, `name`) VALUES
(1, 'admin', 'logentry', NULL),
(2, 'auth', 'permission', NULL),
(3, 'auth', 'group', NULL),
(4, 'auth', 'user', NULL),
(5, 'contenttypes', 'contenttype', NULL),
(6, 'users', 'usuario', NULL),
(7, 'aduaneiro', 'declaracaounica', NULL),
(8, 'governanca', 'assembleia', NULL),
(9, 'governanca', 'atadigital', NULL),
(10, 'governanca', 'manifestointegridade', NULL),
(11, 'governanca', 'notificacao', NULL),
(12, 'governanca', 'pautavotacao', NULL),
(13, 'governanca', 'presencaassembleia', NULL),
(14, 'governanca', 'procuracao', NULL),
(15, 'governanca', 'voto', NULL),
(16, 'governanca', 'recibovoto', NULL),
(17, 'governanca', 'documentoassembleia', NULL),
(18, 'governanca', 'membromesa', NULL),
(19, 'governanca', 'mensagemchat', NULL),
(20, 'governanca', 'carteiraprofissional', NULL),
(21, 'governanca', 'certidaoregularidade', NULL),
(22, 'governanca', 'estadofinanceiro', NULL),
(23, 'governanca', 'quotaconfig', NULL),
(24, 'governanca', 'quotagerada', NULL),
(25, 'governanca', 'pagamentoquota', NULL),
(26, 'governanca', 'artigodocumento', NULL),
(27, 'governanca', 'comentario', NULL),
(28, 'governanca', 'consultapublica', NULL),
(29, 'governanca', 'relatorioconsulta', NULL),
(30, 'governanca', 'votacaoconsulta', NULL),
(31, 'governanca', 'votoconsulta', NULL),
(32, 'governanca', 'convocatoria', NULL),
(33, 'governanca', 'logassembleia', NULL),
(34, 'governanca', 'respostapresenca', NULL),
(35, 'governanca', 'categoriamembro', NULL),
(36, 'governanca', 'isencaomembro', NULL),
(37, 'governanca', 'tipoquota', NULL),
(38, 'governanca', 'historicoquota', NULL);

-- --------------------------------------------------------

--
-- Estrutura da tabela `django_migrations`
--

CREATE TABLE `django_migrations` (
  `id` bigint(20) NOT NULL,
  `app` varchar(255) NOT NULL,
  `name` varchar(255) NOT NULL,
  `applied` datetime(6) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

--
-- Extraindo dados da tabela `django_migrations`
--

INSERT INTO `django_migrations` (`id`, `app`, `name`, `applied`) VALUES
(1, 'contenttypes', '0001_initial', '2026-06-12 13:57:47.505935'),
(2, 'auth', '0001_initial', '2026-06-12 13:57:47.546840'),
(3, 'admin', '0001_initial', '2026-06-12 13:57:47.589332'),
(4, 'admin', '0002_logentry_remove_auto_add', '2026-06-12 13:57:47.609052'),
(5, 'admin', '0003_logentry_add_action_flag_choices', '2026-06-12 13:57:47.626318'),
(6, 'aduaneiro', '0001_initial', '2026-06-12 13:57:47.659595'),
(7, 'aduaneiro', '0002_add_indexes', '2026-06-12 13:57:47.839810'),
(8, 'aduaneiro', '0003_remove_declaracaounica_idx_du_status_and_more', '2026-06-12 13:57:48.439601'),
(9, 'users', '0001_initial', '2026-06-12 16:17:34.374487'),
(10, 'users', '0002_add_indexes', '2026-06-12 16:17:34.405456'),
(11, 'users', '0003_remove_usuario_idx_usuario_papel_status', '2026-06-12 16:17:34.424188'),
(12, 'users', '0004_add_critical_indexes', '2026-06-12 16:17:34.441039'),
(13, 'users', '0005_add_secretario_fields', '2026-06-12 16:17:34.456216'),
(14, 'governanca', '0001_initial', '2026-06-12 16:17:34.471920'),
(15, 'governanca', '0002_voto_opcao_encriptada_voto_recibo_hash_recibovoto', '2026-06-12 16:17:34.486791'),
(16, 'governanca', '0003_alter_procuracao_codigo_otp', '2026-06-12 16:17:34.501409'),
(17, 'governanca', '0004_documentoassembleia', '2026-06-12 16:17:34.516030'),
(18, 'governanca', '0005_membromesa', '2026-06-12 16:17:34.530073'),
(19, 'governanca', '0006_mensagemchat', '2026-06-12 16:17:34.545463'),
(20, 'governanca', '0007_alter_notificacao_options_alter_pautavotacao_options_and_more', '2026-06-12 16:17:34.561014'),
(21, 'governanca', '0008_artigodocumento_alter_notificacao_options_and_more', '2026-06-12 16:17:34.575760'),
(22, 'governanca', '0009_assembleia_max_procuracao_and_more', '2026-06-12 16:17:34.590611'),
(23, 'governanca', '0010_quotaconfig_ativa_quotaconfig_juros_atraso_and_more', '2026-06-12 16:17:34.604730'),
(24, 'governanca', '0011_remove_quotaconfig_juros_atraso_and_more', '2026-06-12 16:17:34.619309'),
(25, 'governanca', '0012_add_indexes', '2026-06-12 16:17:34.637037'),
(26, 'governanca', '0013_remove_assembleia_idx_assembleia_status_and_more', '2026-06-12 16:17:34.651555'),
(27, 'governanca', '0014_documentoassembleia_add_decreto', '2026-06-12 16:17:34.666297'),
(28, 'governanca', '0015_add_critical_indexes', '2026-06-12 16:17:34.683505'),
(29, 'governanca', '0016_categoriamembro_isencaomembro_tipoquota_and_more', '2026-06-12 16:17:34.697921'),
(30, 'users', '0006_usuario_categoria', '2026-06-12 16:17:34.713269'),
(31, 'governanca', '0017_seed_tipos_categorias', '2026-06-12 16:17:34.727851'),
(32, 'governanca', '0018_documentoassembleia_conteudo_and_more', '2026-06-12 16:17:34.744149'),
(33, 'governanca', '0019_simplificar_categorias', '2026-06-12 16:17:34.758802'),
(34, 'governanca', '0020_alter_assembleia_data_hora_alter_assembleia_status_and_more', '2026-06-12 16:17:34.775946'),
(35, 'users', '0007_alter_usuario_papel_alter_usuario_status_and_more', '2026-06-12 16:17:34.789961'),
(36, 'governanca', '0021_mensagemchat_idx_chat_assembleia_data', '2026-06-12 16:17:34.806140'),
(37, 'governanca', '0022_pagamentoquota_status_anterior_quota_and_more', '2026-06-12 16:17:34.822616'),
(38, 'governanca', '0023_rename_dias_limite_retroativo_quotaconfig_meses_limite_retroativo', '2026-06-12 16:17:34.837629'),
(39, 'governanca', '0024_remove_quotaconfig_meses_limite_retroativo_and_more', '2026-06-12 16:17:34.852995'),
(40, 'governanca', '0025_altera_unique_together_voto_delegado_de', '2026-06-12 16:17:34.867815'),
(41, 'governanca', '0026_alter_notificacao_tipo', '2026-06-12 16:17:34.884024'),
(42, 'governanca', '0027_assembleia_ultima_actividade', '2026-06-12 16:21:12.465856'),
(43, 'contenttypes', '0002_remove_content_type_name', '2026-06-12 16:23:09.557722'),
(44, 'aduaneiro', '0004_alter_declaracaounica_status', '2026-06-12 16:23:10.927327'),
(45, 'auth', '0002_alter_permission_name_max_length', '2026-06-12 16:23:13.579202'),
(46, 'auth', '0003_alter_user_email_max_length', '2026-06-12 16:23:13.622596'),
(47, 'auth', '0004_alter_user_username_opts', '2026-06-12 16:23:13.643732'),
(48, 'auth', '0005_alter_user_last_login_null', '2026-06-12 16:23:13.684306'),
(49, 'auth', '0006_require_contenttypes_0002', '2026-06-12 16:23:13.699857'),
(50, 'auth', '0007_alter_validators_add_error_messages', '2026-06-12 16:23:13.721285'),
(51, 'auth', '0008_alter_user_username_max_length', '2026-06-12 16:23:13.763578'),
(52, 'auth', '0009_alter_user_last_name_max_length', '2026-06-12 16:23:13.807997'),
(53, 'auth', '0010_alter_group_name_max_length', '2026-06-12 16:23:13.850114'),
(54, 'auth', '0011_update_proxy_permissions', '2026-06-12 16:23:13.937291'),
(55, 'auth', '0012_alter_user_first_name_max_length', '2026-06-12 16:23:13.977508'),
(56, 'clientes', '0001_initial', '2026-06-12 16:25:01.605002');

-- --------------------------------------------------------

--
-- Estrutura da tabela `django_session`
--

CREATE TABLE `django_session` (
  `session_key` varchar(40) NOT NULL,
  `session_data` longtext NOT NULL,
  `expire_date` datetime(6) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `governanca_artigos_documento`
--

CREATE TABLE `governanca_artigos_documento` (
  `id` bigint(20) NOT NULL,
  `numero` int(11) NOT NULL,
  `titulo` varchar(300) NOT NULL,
  `conteudo` longtext NOT NULL,
  `ordem` int(11) NOT NULL,
  `consulta_id` bigint(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `governanca_assembleias`
--

CREATE TABLE `governanca_assembleias` (
  `id` bigint(20) NOT NULL,
  `titulo` varchar(300) NOT NULL,
  `descricao` longtext NOT NULL,
  `data_hora` datetime(6) NOT NULL,
  `data_encerramento` datetime(6) DEFAULT NULL,
  `local` varchar(300) NOT NULL,
  `link_streaming` varchar(500) NOT NULL,
  `livekit_room` varchar(100) NOT NULL,
  `status` varchar(20) NOT NULL,
  `quorum_minimo` int(11) NOT NULL,
  `total_eleitores` int(11) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `hash_integridade` varchar(64) NOT NULL,
  `created_by_id` bigint(20) DEFAULT NULL,
  `max_procuracao` int(11) NOT NULL,
  `ultima_actividade` datetime(6) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `governanca_atas`
--

CREATE TABLE `governanca_atas` (
  `id` bigint(20) NOT NULL,
  `conteudo` longtext NOT NULL,
  `assinatura_hash` varchar(64) NOT NULL,
  `assinado_em` datetime(6) DEFAULT NULL,
  `publicado_em` datetime(6) DEFAULT NULL,
  `arquivo_pdf` varchar(500) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `assembleia_id` bigint(20) NOT NULL,
  `assinado_por_id` bigint(20) DEFAULT NULL,
  `assinado_presidente_em` datetime(6) DEFAULT NULL,
  `assinado_secretario_em` datetime(6) DEFAULT NULL,
  `assinatura_hash_presidente` varchar(64) NOT NULL,
  `assinatura_hash_secretario` varchar(64) NOT NULL,
  `status_assinatura` varchar(25) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `governanca_carteiras_profissionais`
--

CREATE TABLE `governanca_carteiras_profissionais` (
  `id` bigint(20) NOT NULL,
  `numero_carteira` varchar(50) NOT NULL,
  `data_emissao` date NOT NULL,
  `data_validade` date NOT NULL,
  `data_renovacao` date DEFAULT NULL,
  `arquivo_pdf` varchar(500) NOT NULL,
  `status` varchar(15) NOT NULL,
  `despachante_id` bigint(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `governanca_categorias_membro`
--

CREATE TABLE `governanca_categorias_membro` (
  `id` bigint(20) NOT NULL,
  `nome` varchar(100) NOT NULL,
  `slug` varchar(100) NOT NULL,
  `isento` tinyint(1) NOT NULL,
  `ordem` int(11) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `governanca_certidoes_regularidade`
--

CREATE TABLE `governanca_certidoes_regularidade` (
  `id` bigint(20) NOT NULL,
  `codigo_certidao` varchar(36) NOT NULL,
  `data_emissao` datetime(6) NOT NULL,
  `data_validade` date NOT NULL,
  `arquivo_pdf` varchar(500) NOT NULL,
  `assinatura_hash` varchar(64) NOT NULL,
  `despachante_id` bigint(20) NOT NULL,
  `emitido_por_id` bigint(20) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `governanca_chat`
--

CREATE TABLE `governanca_chat` (
  `id` bigint(20) NOT NULL,
  `tipo` varchar(10) NOT NULL,
  `texto` longtext NOT NULL,
  `reacao` varchar(10) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `assembleia_id` bigint(20) NOT NULL,
  `usuario_id` bigint(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `governanca_comentarios_consulta`
--

CREATE TABLE `governanca_comentarios_consulta` (
  `id` bigint(20) NOT NULL,
  `texto` longtext NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `artigo_id` bigint(20) NOT NULL,
  `autor_id` bigint(20) NOT NULL,
  `resposta_a_id` bigint(20) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `governanca_consultas_publicas`
--

CREATE TABLE `governanca_consultas_publicas` (
  `id` bigint(20) NOT NULL,
  `titulo` varchar(300) NOT NULL,
  `descricao` longtext NOT NULL,
  `documento` varchar(500) NOT NULL,
  `prazo_fim` datetime(6) DEFAULT NULL,
  `status` varchar(20) NOT NULL,
  `publicado_em` datetime(6) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `criado_por_id` bigint(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `governanca_convocatorias`
--

CREATE TABLE `governanca_convocatorias` (
  `id` bigint(20) NOT NULL,
  `titulo` varchar(300) NOT NULL,
  `descricao` longtext NOT NULL,
  `documento` varchar(500) NOT NULL,
  `data_envio` datetime(6) NOT NULL,
  `prazo_confirmacao` datetime(6) DEFAULT NULL,
  `status` varchar(20) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `assembleia_id` bigint(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `governanca_documentos`
--

CREATE TABLE `governanca_documentos` (
  `id` bigint(20) NOT NULL,
  `tipo` varchar(20) NOT NULL,
  `titulo` varchar(300) NOT NULL,
  `descricao` longtext NOT NULL,
  `arquivo` varchar(500) DEFAULT NULL,
  `publicado` tinyint(1) NOT NULL,
  `publicado_em` datetime(6) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL,
  `assembleia_id` bigint(20) NOT NULL,
  `created_by_id` bigint(20) DEFAULT NULL,
  `conteudo` longtext NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `governanca_estado_financeiro`
--

CREATE TABLE `governanca_estado_financeiro` (
  `id` bigint(20) NOT NULL,
  `estado` varchar(15) NOT NULL,
  `ultima_atualizacao` datetime(6) NOT NULL,
  `observacoes` longtext NOT NULL,
  `despachante_id` bigint(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

--
-- Extraindo dados da tabela `governanca_estado_financeiro`
--

INSERT INTO `governanca_estado_financeiro` (`id`, `estado`, `ultima_atualizacao`, `observacoes`, `despachante_id`) VALUES
(1, 'Regular', '2026-06-08 16:50:22.915032', '', 4),
(2, 'Regular', '2026-06-09 10:26:18.468189', '', 5),
(3, 'Regular', '2026-06-09 13:42:54.262306', '', 6);

-- --------------------------------------------------------

--
-- Estrutura da tabela `governanca_historico_quotas`
--

CREATE TABLE `governanca_historico_quotas` (
  `id` bigint(20) NOT NULL,
  `acao` varchar(30) NOT NULL,
  `descricao` longtext NOT NULL,
  `ip` char(39) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL,
  `membro_id` bigint(20) NOT NULL,
  `pagamento_id` bigint(20) DEFAULT NULL,
  `quota_id` bigint(20) DEFAULT NULL,
  `utilizador_id` bigint(20) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `governanca_isencoes_membro`
--

CREATE TABLE `governanca_isencoes_membro` (
  `id` bigint(20) NOT NULL,
  `data_inicio` date NOT NULL,
  `data_fim` date DEFAULT NULL,
  `motivo` longtext NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `aprovado_por_id` bigint(20) DEFAULT NULL,
  `despachante_id` bigint(20) NOT NULL,
  `tipo_quota_id` bigint(20) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `governanca_logs_assembleia`
--

CREATE TABLE `governanca_logs_assembleia` (
  `id` bigint(20) NOT NULL,
  `acao` varchar(30) NOT NULL,
  `detalhes` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL CHECK (json_valid(`detalhes`)),
  `ip` char(39) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL,
  `assembleia_id` bigint(20) NOT NULL,
  `usuario_id` bigint(20) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `governanca_manifestos`
--

CREATE TABLE `governanca_manifestos` (
  `id` bigint(20) NOT NULL,
  `hash_consolidado` varchar(64) NOT NULL,
  `dados_json` longtext NOT NULL,
  `gerado_em` datetime(6) NOT NULL,
  `assembleia_id` bigint(20) NOT NULL,
  `gerado_por_id` bigint(20) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `governanca_mesa`
--

CREATE TABLE `governanca_mesa` (
  `id` bigint(20) NOT NULL,
  `funcao` varchar(30) NOT NULL,
  `ordem` int(11) NOT NULL,
  `assembleia_id` bigint(20) NOT NULL,
  `usuario_id` bigint(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `governanca_notificacoes`
--

CREATE TABLE `governanca_notificacoes` (
  `id` bigint(20) NOT NULL,
  `tipo` varchar(30) NOT NULL,
  `titulo` varchar(300) NOT NULL,
  `mensagem` longtext NOT NULL,
  `link` varchar(500) NOT NULL,
  `lida` tinyint(1) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `usuario_id` bigint(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `governanca_pagamentos_quota`
--

CREATE TABLE `governanca_pagamentos_quota` (
  `id` bigint(20) NOT NULL,
  `metodo` varchar(30) NOT NULL,
  `comprovativo` varchar(500) NOT NULL,
  `valor_pago` decimal(12,2) NOT NULL,
  `codigo_transferencia` varchar(100) NOT NULL,
  `iban_origem` varchar(50) NOT NULL,
  `data_pagamento` datetime(6) NOT NULL,
  `status` varchar(25) NOT NULL,
  `confirmado_em` datetime(6) DEFAULT NULL,
  `observacoes` longtext NOT NULL,
  `confirmado_por_id` bigint(20) DEFAULT NULL,
  `despachante_id` bigint(20) NOT NULL,
  `quota_id` bigint(20) NOT NULL,
  `status_anterior_quota` varchar(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `governanca_pautas`
--

CREATE TABLE `governanca_pautas` (
  `id` bigint(20) NOT NULL,
  `titulo` varchar(300) NOT NULL,
  `descricao` longtext NOT NULL,
  `ordem` int(11) NOT NULL,
  `tipo_votacao` varchar(20) NOT NULL,
  `status` varchar(20) NOT NULL,
  `resultado_final` varchar(50) NOT NULL,
  `iniciado_em` datetime(6) DEFAULT NULL,
  `encerrado_em` datetime(6) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL,
  `assembleia_id` bigint(20) NOT NULL,
  `reaberta` tinyint(1) NOT NULL,
  `reaberta_em` datetime(6) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `governanca_presencas`
--

CREATE TABLE `governanca_presencas` (
  `id` bigint(20) NOT NULL,
  `presente_em` datetime(6) DEFAULT NULL,
  `saiu_em` datetime(6) DEFAULT NULL,
  `ip_registro` char(39) DEFAULT NULL,
  `assembleia_id` bigint(20) NOT NULL,
  `usuario_id` bigint(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `governanca_procuracao`
--

CREATE TABLE `governanca_procuracao` (
  `id` bigint(20) NOT NULL,
  `codigo_otp` varchar(64) NOT NULL,
  `status` varchar(20) NOT NULL,
  `confirmado_em` datetime(6) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL,
  `assembleia_id` bigint(20) NOT NULL,
  `outorgado_id` bigint(20) NOT NULL,
  `outorgante_id` bigint(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `governanca_quotas_geradas`
--

CREATE TABLE `governanca_quotas_geradas` (
  `id` bigint(20) NOT NULL,
  `ano` int(11) DEFAULT NULL,
  `mes` int(11) DEFAULT NULL,
  `valor` decimal(12,2) NOT NULL,
  `data_vencimento` date NOT NULL,
  `data_pagamento` datetime(6) DEFAULT NULL,
  `status` varchar(20) NOT NULL,
  `fatura_uuid` varchar(36) NOT NULL,
  `observacoes` longtext NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `despachante_id` bigint(20) NOT NULL,
  `descricao` varchar(300) NOT NULL,
  `periodo_fim` date DEFAULT NULL,
  `periodo_inicio` date DEFAULT NULL,
  `tipo_id` bigint(20) DEFAULT NULL,
  `data_envio` date DEFAULT NULL,
  `referencia` varchar(100) DEFAULT NULL,
  `valor_multa` decimal(12,2) NOT NULL,
  `valor_original` decimal(12,2) DEFAULT NULL,
  `valor_total` decimal(12,2) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `governanca_quota_config`
--

CREATE TABLE `governanca_quota_config` (
  `id` bigint(20) NOT NULL,
  `ano` int(11) NOT NULL,
  `mes` int(11) DEFAULT NULL,
  `valor` decimal(12,2) NOT NULL,
  `data_vencimento` date NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `ativa` tinyint(1) NOT NULL,
  `multa_percentual` decimal(5,2) NOT NULL,
  `categoria_id` bigint(20) DEFAULT NULL,
  `tipo_id` bigint(20) DEFAULT NULL,
  `dias_carencia` smallint(5) UNSIGNED NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `governanca_recibos_voto`
--

CREATE TABLE `governanca_recibos_voto` (
  `id` bigint(20) NOT NULL,
  `recibo_hash` varchar(64) NOT NULL,
  `pauta_titulo` varchar(300) NOT NULL,
  `data_voto` datetime(6) NOT NULL,
  `verificado` tinyint(1) NOT NULL,
  `voto_id` bigint(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `governanca_relatorios_consulta`
--

CREATE TABLE `governanca_relatorios_consulta` (
  `id` bigint(20) NOT NULL,
  `conteudo` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL CHECK (json_valid(`conteudo`)),
  `assinatura_hash` varchar(64) NOT NULL,
  `arquivo_pdf` varchar(500) NOT NULL,
  `criado_em` datetime(6) NOT NULL,
  `consulta_id` bigint(20) NOT NULL,
  `criado_por_id` bigint(20) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `governanca_respostas_presenca`
--

CREATE TABLE `governanca_respostas_presenca` (
  `id` bigint(20) NOT NULL,
  `resposta` varchar(10) NOT NULL,
  `respondido_em` datetime(6) NOT NULL,
  `assembleia_id` bigint(20) NOT NULL,
  `usuario_id` bigint(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `governanca_tipos_quota`
--

CREATE TABLE `governanca_tipos_quota` (
  `id` bigint(20) NOT NULL,
  `nome` varchar(100) NOT NULL,
  `slug` varchar(100) NOT NULL,
  `recorrente` tinyint(1) NOT NULL,
  `dias_intervalo` int(11) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `governanca_votacoes_consulta`
--

CREATE TABLE `governanca_votacoes_consulta` (
  `id` bigint(20) NOT NULL,
  `data_inicio` datetime(6) NOT NULL,
  `data_fim` datetime(6) DEFAULT NULL,
  `ativa` tinyint(1) NOT NULL,
  `consulta_id` bigint(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `governanca_votos`
--

CREATE TABLE `governanca_votos` (
  `id` bigint(20) NOT NULL,
  `opcao` varchar(20) NOT NULL,
  `em_delegacao` tinyint(1) NOT NULL,
  `hash_auditoria` varchar(64) NOT NULL,
  `votado_em` datetime(6) NOT NULL,
  `delegado_de_id` bigint(20) DEFAULT NULL,
  `pauta_id` bigint(20) NOT NULL,
  `usuario_id` bigint(20) NOT NULL,
  `opcao_encriptada` varchar(128) NOT NULL,
  `recibo_hash` varchar(64) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `governanca_votos_consulta`
--

CREATE TABLE `governanca_votos_consulta` (
  `id` bigint(20) NOT NULL,
  `voto` varchar(10) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `usuario_id` bigint(20) NOT NULL,
  `votacao_id` bigint(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `permissoes`
--

CREATE TABLE `permissoes` (
  `id` bigint(20) NOT NULL,
  `codigo` varchar(100) NOT NULL,
  `nome` varchar(200) NOT NULL,
  `descricao` longtext NOT NULL,
  `grupo` varchar(100) NOT NULL,
  `icone` varchar(50) NOT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `permissoes_cargo`
--

CREATE TABLE `permissoes_cargo` (
  `id` bigint(20) NOT NULL,
  `codigo` varchar(100) NOT NULL,
  `nome` varchar(100) NOT NULL,
  `descricao` longtext NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

--
-- Extraindo dados da tabela `permissoes_cargo`
--

INSERT INTO `permissoes_cargo` (`id`, `codigo`, `nome`, `descricao`) VALUES
(1, 'ver_secretaria', 'Ver Secretaria', 'Acesso à secção Secretaria e seus documentos'),
(2, 'gerir_quotas', 'Gerir Quotas', 'Atribuir, definir e editar quotas'),
(3, 'ver_gestao_financeira', 'Ver Gestão Financeira', 'Visualizar o painel financeiro'),
(4, 'gerir_assembleia', 'Gerir Assembleia', 'Convocar, editar e gerir assembleias'),
(5, 'ver_rh', 'Ver RH', 'Acesso à secção de Recursos Humanos');

-- --------------------------------------------------------

--
-- Estrutura da tabela `rh_avaliacoes`
--

CREATE TABLE `rh_avaliacoes` (
  `id` bigint(20) NOT NULL,
  `pontualidade` smallint(5) UNSIGNED NOT NULL,
  `produtividade` smallint(5) UNSIGNED NOT NULL,
  `qualidade_trabalho` smallint(5) UNSIGNED NOT NULL,
  `trabalho_equipa` smallint(5) UNSIGNED NOT NULL,
  `iniciativa` smallint(5) UNSIGNED NOT NULL,
  `nota_global` decimal(3,1) NOT NULL,
  `pontos_fortes` longtext NOT NULL,
  `pontos_melhoria` longtext NOT NULL,
  `plano_desenvolvimento` longtext NOT NULL,
  `criado_em` datetime(6) NOT NULL,
  `ciclo_id` bigint(20) NOT NULL,
  `colaborador_id` bigint(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `rh_candidaturas`
--

CREATE TABLE `rh_candidaturas` (
  `id` bigint(20) NOT NULL,
  `nome` varchar(255) NOT NULL,
  `email` varchar(254) NOT NULL,
  `telefone` varchar(30) NOT NULL,
  `cv` varchar(100) DEFAULT NULL,
  `carta_motivacao` longtext NOT NULL,
  `estado` varchar(15) NOT NULL,
  `data_entrevista` datetime(6) DEFAULT NULL,
  `notas` longtext NOT NULL,
  `criado_em` datetime(6) NOT NULL,
  `vaga_id` bigint(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `rh_cargos_mesa`
--

CREATE TABLE `rh_cargos_mesa` (
  `id` bigint(20) NOT NULL,
  `funcao` varchar(30) NOT NULL,
  `atribuido_em` datetime(6) NOT NULL,
  `usuario_id` bigint(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `rh_ciclos_avaliacao`
--

CREATE TABLE `rh_ciclos_avaliacao` (
  `id` bigint(20) NOT NULL,
  `nome` varchar(200) NOT NULL,
  `periodo_inicio` date NOT NULL,
  `periodo_fim` date NOT NULL,
  `estado` varchar(10) NOT NULL,
  `criado_em` datetime(6) NOT NULL,
  `banca_id` bigint(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `rh_colaboradores`
--

CREATE TABLE `rh_colaboradores` (
  `id` bigint(20) NOT NULL,
  `nome` varchar(255) NOT NULL,
  `bi` varchar(50) NOT NULL,
  `nif` varchar(50) NOT NULL,
  `genero` varchar(1) NOT NULL,
  `data_nascimento` date DEFAULT NULL,
  `cargo` varchar(30) NOT NULL,
  `cargo_personalizado` varchar(100) NOT NULL,
  `departamento` varchar(100) NOT NULL,
  `email` varchar(254) NOT NULL,
  `telefone` varchar(30) NOT NULL,
  `data_admissao` date DEFAULT NULL,
  `salario_base` decimal(12,2) DEFAULT NULL,
  `estado` varchar(10) NOT NULL,
  `foto` varchar(100) DEFAULT NULL,
  `observacoes` longtext NOT NULL,
  `criado_em` datetime(6) NOT NULL,
  `atualizado_em` datetime(6) NOT NULL,
  `banca_id` bigint(20) NOT NULL,
  `filial_id` bigint(20) DEFAULT NULL,
  `usuario_id` int(11) DEFAULT NULL,
  `password` varchar(255) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `rh_colaborador_documentos`
--

CREATE TABLE `rh_colaborador_documentos` (
  `id` bigint(20) NOT NULL,
  `tipo` varchar(20) NOT NULL,
  `arquivo` varchar(100) NOT NULL,
  `descricao` varchar(255) NOT NULL,
  `criado_em` datetime(6) NOT NULL,
  `colaborador_id` bigint(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `rh_empresas`
--

CREATE TABLE `rh_empresas` (
  `id` bigint(20) NOT NULL,
  `usuario_id` int(11) NOT NULL,
  `nome` varchar(255) NOT NULL,
  `nif` varchar(50) NOT NULL,
  `tipo` varchar(20) NOT NULL,
  `email` varchar(254) NOT NULL,
  `telefone` varchar(30) NOT NULL,
  `endereco` longtext NOT NULL,
  `provincia` varchar(100) NOT NULL,
  `municipio` varchar(100) NOT NULL,
  `licenca_cdoa` varchar(100) NOT NULL,
  `logo` varchar(100) DEFAULT NULL,
  `ativa` tinyint(1) NOT NULL,
  `criado_em` datetime(6) NOT NULL,
  `atualizado_em` datetime(6) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `rh_entrevistas`
--

CREATE TABLE `rh_entrevistas` (
  `id` bigint(20) NOT NULL,
  `data_hora` datetime(6) NOT NULL,
  `tipo` varchar(15) NOT NULL,
  `local_link` varchar(300) NOT NULL,
  `entrevistador` varchar(255) NOT NULL,
  `resultado` varchar(15) NOT NULL,
  `nota` smallint(5) UNSIGNED DEFAULT NULL,
  `observacoes` longtext NOT NULL,
  `criado_em` datetime(6) NOT NULL,
  `candidatura_id` bigint(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `rh_faturas`
--

CREATE TABLE `rh_faturas` (
  `id` bigint(20) NOT NULL,
  `codigo` varchar(50) NOT NULL,
  `tipo` varchar(25) NOT NULL,
  `estado` varchar(15) NOT NULL,
  `valor_bruto` decimal(15,2) NOT NULL,
  `valor_liquido` decimal(15,2) NOT NULL,
  `valor_imposto` decimal(15,2) NOT NULL,
  `data_emissao` datetime(6) NOT NULL,
  `data_vencimento` date NOT NULL,
  `data_pagamento` datetime(6) DEFAULT NULL,
  `descricao` longtext NOT NULL,
  `observacoes` longtext NOT NULL,
  `criado_por` int(11) DEFAULT NULL,
  `atualizado_em` datetime(6) NOT NULL,
  `banca_id` bigint(20) NOT NULL,
  `colaborador_id` bigint(20) DEFAULT NULL,
  `processamento_salarial_id` bigint(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `rh_filiais`
--

CREATE TABLE `rh_filiais` (
  `id` bigint(20) NOT NULL,
  `provincia` varchar(100) NOT NULL,
  `municipio` varchar(100) NOT NULL,
  `endereco` longtext NOT NULL,
  `telefone` varchar(30) NOT NULL,
  `email` varchar(254) NOT NULL,
  `responsavel` varchar(255) NOT NULL,
  `ativa` tinyint(1) NOT NULL,
  `criado_em` datetime(6) NOT NULL,
  `banca_id` bigint(20) NOT NULL,
  `tem_responsavel` tinyint(1) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `rh_gestores_filial`
--

CREATE TABLE `rh_gestores_filial` (
  `id` bigint(20) NOT NULL,
  `ativo` tinyint(1) NOT NULL,
  `nome_gestor` varchar(255) NOT NULL,
  `criado_em` datetime(6) NOT NULL,
  `atualizado_em` datetime(6) NOT NULL,
  `colaborador_id` bigint(20) NOT NULL,
  `filial_id` bigint(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `rh_metricas_avaliacao`
--

CREATE TABLE `rh_metricas_avaliacao` (
  `id` bigint(20) NOT NULL,
  `nome` varchar(100) NOT NULL,
  `descricao` varchar(255) NOT NULL,
  `ordem` smallint(5) UNSIGNED NOT NULL,
  `ciclo_id` bigint(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `rh_notas_metricas`
--

CREATE TABLE `rh_notas_metricas` (
  `id` bigint(20) NOT NULL,
  `nota` smallint(5) UNSIGNED NOT NULL,
  `avaliacao_id` bigint(20) NOT NULL,
  `metrica_id` bigint(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `rh_pedidos_ferias`
--

CREATE TABLE `rh_pedidos_ferias` (
  `id` bigint(20) NOT NULL,
  `data_inicio` date NOT NULL,
  `data_fim` date NOT NULL,
  `motivo` longtext NOT NULL,
  `estado` varchar(10) NOT NULL,
  `criado_em` datetime(6) NOT NULL,
  `colaborador_id` bigint(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `rh_planos_integracao`
--

CREATE TABLE `rh_planos_integracao` (
  `id` bigint(20) NOT NULL,
  `data_inicio` date NOT NULL,
  `data_fim_prevista` date DEFAULT NULL,
  `responsavel` varchar(255) NOT NULL,
  `estado` varchar(10) NOT NULL,
  `notas` longtext NOT NULL,
  `criado_em` datetime(6) NOT NULL,
  `candidatura_id` bigint(20) NOT NULL,
  `colaborador_id` bigint(20) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `rh_presencas`
--

CREATE TABLE `rh_presencas` (
  `id` bigint(20) NOT NULL,
  `data` date NOT NULL,
  `tipo` varchar(20) NOT NULL,
  `hora_entrada` time(6) DEFAULT NULL,
  `hora_saida` time(6) DEFAULT NULL,
  `horas_extras` decimal(4,1) NOT NULL,
  `justificacao` longtext NOT NULL,
  `estado` varchar(10) NOT NULL,
  `criado_em` datetime(6) NOT NULL,
  `colaborador_id` bigint(20) NOT NULL,
  `aprovado_por_id` bigint(20) DEFAULT NULL,
  `data_aprovacao` datetime(6) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `rh_processamentos`
--

CREATE TABLE `rh_processamentos` (
  `id` bigint(20) NOT NULL,
  `mes` smallint(5) UNSIGNED NOT NULL,
  `ano` smallint(5) UNSIGNED NOT NULL,
  `estado` varchar(15) NOT NULL,
  `criado_em` datetime(6) NOT NULL,
  `processado_em` datetime(6) DEFAULT NULL,
  `banca_id` bigint(20) NOT NULL,
  `pdf_gerado` tinyint(1) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `rh_recibos`
--

CREATE TABLE `rh_recibos` (
  `id` bigint(20) NOT NULL,
  `salario_base` decimal(12,2) NOT NULL,
  `subsidio_alimentacao` decimal(10,2) NOT NULL,
  `subsidio_transporte` decimal(10,2) NOT NULL,
  `outros_subsidios` decimal(10,2) NOT NULL,
  `horas_extras_valor` decimal(10,2) NOT NULL,
  `irt` decimal(10,2) NOT NULL,
  `inss_trabalhador` decimal(10,2) NOT NULL,
  `inss_entidade` decimal(10,2) NOT NULL,
  `outros_descontos` decimal(10,2) NOT NULL,
  `observacoes` longtext NOT NULL,
  `colaborador_id` bigint(20) NOT NULL,
  `processamento_id` bigint(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `rh_recibo_subsidios`
--

CREATE TABLE `rh_recibo_subsidios` (
  `id` bigint(20) NOT NULL,
  `valor` decimal(12,2) NOT NULL,
  `valor_padrao` decimal(12,2) NOT NULL,
  `observacoes` longtext NOT NULL,
  `criado_em` datetime(6) NOT NULL,
  `recibo_id` bigint(20) NOT NULL,
  `subsidio_id` bigint(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `rh_subsidios`
--

CREATE TABLE `rh_subsidios` (
  `id` bigint(20) NOT NULL,
  `nome` varchar(100) NOT NULL,
  `codigo` varchar(20) NOT NULL,
  `tipo_calculo` varchar(20) NOT NULL,
  `valor_padrao` decimal(12,2) NOT NULL,
  `percentual` decimal(5,2) DEFAULT NULL,
  `ativo` tinyint(1) NOT NULL,
  `obrigatorio` tinyint(1) NOT NULL,
  `descricao` longtext NOT NULL,
  `criado_em` datetime(6) NOT NULL,
  `atualizado_em` datetime(6) NOT NULL,
  `banca_id` bigint(20) NOT NULL,
  `apenas_especificos` tinyint(1) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `rh_subsidios_colaboradores_especificos`
--

CREATE TABLE `rh_subsidios_colaboradores_especificos` (
  `id` bigint(20) NOT NULL,
  `subsidio_id` bigint(20) NOT NULL,
  `colaborador_id` bigint(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `rh_tarefas_integracao`
--

CREATE TABLE `rh_tarefas_integracao` (
  `id` bigint(20) NOT NULL,
  `titulo` varchar(200) NOT NULL,
  `descricao` longtext NOT NULL,
  `responsavel` varchar(255) NOT NULL,
  `prazo` date DEFAULT NULL,
  `concluida` tinyint(1) NOT NULL,
  `criado_em` datetime(6) NOT NULL,
  `plano_id` bigint(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `rh_vagas`
--

CREATE TABLE `rh_vagas` (
  `id` bigint(20) NOT NULL,
  `titulo` varchar(200) NOT NULL,
  `departamento` varchar(100) NOT NULL,
  `descricao` longtext NOT NULL,
  `requisitos` longtext NOT NULL,
  `salario_min` decimal(12,2) DEFAULT NULL,
  `salario_max` decimal(12,2) DEFAULT NULL,
  `vagas_numero` smallint(5) UNSIGNED NOT NULL,
  `estado` varchar(15) NOT NULL,
  `data_abertura` date NOT NULL,
  `data_encerramento` date DEFAULT NULL,
  `criado_em` datetime(6) NOT NULL,
  `banca_id` bigint(20) NOT NULL,
  `filial_id` bigint(20) DEFAULT NULL,
  `link_externo` char(32) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- Estrutura da tabela `usuarios`
--

CREATE TABLE `usuarios` (
  `id` bigint(20) NOT NULL,
  `username` varchar(50) NOT NULL,
  `password` varchar(255) DEFAULT NULL,
  `nome` varchar(100) NOT NULL,
  `email` varchar(100) NOT NULL,
  `foto` varchar(255) DEFAULT NULL,
  `telefone` varchar(20) DEFAULT NULL,
  `cedula` varchar(50) DEFAULT NULL,
  `papel` varchar(50) NOT NULL,
  `status` varchar(10) NOT NULL,
  `sso_portal_id` int(11) DEFAULT NULL,
  `ultimo_acesso` datetime(6) DEFAULT NULL,
  `nif` longtext NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `is_secretario` tinyint(1) NOT NULL DEFAULT 0,
  `is_vice_secretario` tinyint(1) NOT NULL DEFAULT 0,
  `categoria_id` bigint(20) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

--
-- Extraindo dados da tabela `usuarios`
--

INSERT INTO `usuarios` (`id`, `username`, `password`, `nome`, `email`, `foto`, `telefone`, `cedula`, `papel`, `status`, `sso_portal_id`, `ultimo_acesso`, `nif`, `created_at`, `updated_at`, `is_secretario`, `is_vice_secretario`, `categoria_id`) VALUES
(1, 'admin', '$2y$10$aIwU.beVp1Ylx51km/YrSuZ1vG338FAABo82M0LmQzccYL.5Ky2Ie', 'Administrador', 'informatica@cdoangola.co.ao', NULL, NULL, NULL, 'Administrador', 'Ativo', NULL, '2026-06-09 09:31:42.372590', '000000000', '2026-05-29 13:25:12.387733', '2026-05-30 03:47:58.000000', 0, 0, 7),
(4, 'adilsona87', NULL, 'Adilson Abel', 'adilsona87@gmail.com', NULL, '922345345', '09778', 'Despachante Oficial', 'Ativo', 660, '2026-06-12 09:23:14.683015', '3333333333', '2026-06-08 16:41:08.940111', '2026-06-12 09:23:14.667864', 0, 0, NULL),
(5, 'honoriomavendadespoficial', NULL, 'Honório Fernandes Joaquim Mavemba', 'honoriomavendadespoficial@gmail.com', NULL, '', '07100', 'Despachante Oficial', 'Ativo', 424, '2026-06-12 08:49:41.586128', '000135931KN035', '2026-06-09 10:03:10.366359', '2026-06-12 08:49:41.571644', 0, 0, NULL),
(6, 'wamanuel1', NULL, 'Walter Antonio Manuel Manuel', 'wamanuel1@gmail.com', NULL, '938979995', '07220', 'Despachante Oficial', 'Ativo', 228, '2026-06-09 14:35:02.613360', '000067967LA02', '2026-06-09 13:34:29.642340', '2026-06-09 14:35:02.596832', 0, 0, NULL);

-- --------------------------------------------------------

--
-- Estrutura da tabela `usuarios_cargos`
--

CREATE TABLE `usuarios_cargos` (
  `id` bigint(20) NOT NULL,
  `atribuido_em` datetime(6) NOT NULL,
  `atribuido_por_id` bigint(20) DEFAULT NULL,
  `cargo_id` bigint(20) NOT NULL,
  `usuario_id` bigint(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

--
-- Índices para tabelas despejadas
--

--
-- Índices para tabela `auth_group`
--
ALTER TABLE `auth_group`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `name` (`name`);

--
-- Índices para tabela `auth_group_permissions`
--
ALTER TABLE `auth_group_permissions`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `auth_group_permissions_group_id_permission_id_0cd325b0_uniq` (`group_id`,`permission_id`),
  ADD KEY `auth_group_permissio_permission_id_84c5c92e_fk_auth_perm` (`permission_id`);

--
-- Índices para tabela `auth_permission`
--
ALTER TABLE `auth_permission`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `auth_permission_content_type_id_codename_01ab375a_uniq` (`content_type_id`,`codename`);

--
-- Índices para tabela `auth_user`
--
ALTER TABLE `auth_user`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `username` (`username`);

--
-- Índices para tabela `auth_user_groups`
--
ALTER TABLE `auth_user_groups`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `auth_user_groups_user_id_group_id_94350c0c_uniq` (`user_id`,`group_id`),
  ADD KEY `auth_user_groups_group_id_97559544_fk_auth_group_id` (`group_id`);

--
-- Índices para tabela `auth_user_user_permissions`
--
ALTER TABLE `auth_user_user_permissions`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `auth_user_user_permissions_user_id_permission_id_14a6b632_uniq` (`user_id`,`permission_id`),
  ADD KEY `auth_user_user_permi_permission_id_1fbb5f2c_fk_auth_perm` (`permission_id`);

--
-- Índices para tabela `cargos`
--
ALTER TABLE `cargos`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `nome` (`nome`),
  ADD UNIQUE KEY `slug` (`slug`);

--
-- Índices para tabela `cargos_permissoes`
--
ALTER TABLE `cargos_permissoes`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `cargos_permissoes_cargo_id_permissao_id_27cf5e40_uniq` (`cargo_id`,`permissao_id`),
  ADD KEY `cargos_permissoes_permissao_id_d6ba7a05_fk_permissoes_id` (`permissao_id`);

--
-- Índices para tabela `clientes_clientes`
--
ALTER TABLE `clientes_clientes`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `nif` (`nif`),
  ADD KEY `clientes_clientes_usuario_id_01115fcd` (`usuario_id`);

--
-- Índices para tabela `declaracoes_unicas`
--
ALTER TABLE `declaracoes_unicas`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `numero_du` (`numero_du`),
  ADD UNIQUE KEY `codigo_processo` (`codigo_processo`),
  ADD KEY `declaracoes_unicas_usuario_id_40ac8f79` (`usuario_id`),
  ADD KEY `declaracoes_unicas_status_d7f17e52` (`status`);

--
-- Índices para tabela `django_admin_log`
--
ALTER TABLE `django_admin_log`
  ADD PRIMARY KEY (`id`),
  ADD KEY `django_admin_log_content_type_id_c4bce8eb_fk_django_co` (`content_type_id`),
  ADD KEY `django_admin_log_user_id_c564eba6_fk_auth_user_id` (`user_id`);

--
-- Índices para tabela `django_apscheduler_djangojob`
--
ALTER TABLE `django_apscheduler_djangojob`
  ADD PRIMARY KEY (`id`),
  ADD KEY `django_apscheduler_djangojob_next_run_time_2f022619` (`next_run_time`);

--
-- Índices para tabela `django_apscheduler_djangojobexecution`
--
ALTER TABLE `django_apscheduler_djangojobexecution`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `unique_job_executions` (`job_id`,`run_time`),
  ADD KEY `django_apscheduler_djangojobexecution_run_time_16edd96b` (`run_time`);

--
-- Índices para tabela `django_content_type`
--
ALTER TABLE `django_content_type`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `django_content_type_app_label_model_76bd3d3b_uniq` (`app_label`,`model`);

--
-- Índices para tabela `django_migrations`
--
ALTER TABLE `django_migrations`
  ADD PRIMARY KEY (`id`);

--
-- Índices para tabela `django_session`
--
ALTER TABLE `django_session`
  ADD PRIMARY KEY (`session_key`),
  ADD KEY `django_session_expire_date_a5c62663` (`expire_date`);

--
-- Índices para tabela `governanca_artigos_documento`
--
ALTER TABLE `governanca_artigos_documento`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `governanca_artigos_documento_consulta_id_numero_6c440173_uniq` (`consulta_id`,`numero`);

--
-- Índices para tabela `governanca_assembleias`
--
ALTER TABLE `governanca_assembleias`
  ADD PRIMARY KEY (`id`),
  ADD KEY `governanca_assembleias_created_by_id_e7c7ac68_fk_usuarios_id` (`created_by_id`),
  ADD KEY `governanca_assembleias_data_hora_01097ca1` (`data_hora`),
  ADD KEY `governanca_assembleias_status_a0fb3d82` (`status`);

--
-- Índices para tabela `governanca_atas`
--
ALTER TABLE `governanca_atas`
  ADD PRIMARY KEY (`id`),
  ADD KEY `governanca_atas_assinado_por_id_6b67f54b_fk_usuarios_id` (`assinado_por_id`),
  ADD KEY `governanca_atas_assembleia_id_23d2d6de` (`assembleia_id`),
  ADD KEY `governanca_atas_status_assinatura_18ece4d3` (`status_assinatura`);

--
-- Índices para tabela `governanca_carteiras_profissionais`
--
ALTER TABLE `governanca_carteiras_profissionais`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `numero_carteira` (`numero_carteira`),
  ADD UNIQUE KEY `despachante_id` (`despachante_id`),
  ADD KEY `governanca_carteiras_profissionais_status_807759da` (`status`);

--
-- Índices para tabela `governanca_categorias_membro`
--
ALTER TABLE `governanca_categorias_membro`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `slug` (`slug`);

--
-- Índices para tabela `governanca_certidoes_regularidade`
--
ALTER TABLE `governanca_certidoes_regularidade`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `codigo_certidao` (`codigo_certidao`),
  ADD KEY `governanca_certidoes_emitido_por_id_e52ff186_fk_usuarios_` (`emitido_por_id`),
  ADD KEY `governanca_certidoes_regularidade_despachante_id_1f3d5736` (`despachante_id`);

--
-- Índices para tabela `governanca_chat`
--
ALTER TABLE `governanca_chat`
  ADD PRIMARY KEY (`id`),
  ADD KEY `governanca_chat_usuario_id_280934ab_fk_usuarios_id` (`usuario_id`),
  ADD KEY `governanca_chat_assembleia_id_29ffc0f9` (`assembleia_id`),
  ADD KEY `idx_chat_assembleia_data` (`assembleia_id`,`created_at` DESC);

--
-- Índices para tabela `governanca_comentarios_consulta`
--
ALTER TABLE `governanca_comentarios_consulta`
  ADD PRIMARY KEY (`id`),
  ADD KEY `governanca_comentari_artigo_id_6390452b_fk_governanc` (`artigo_id`),
  ADD KEY `governanca_comentarios_consulta_autor_id_3e436a4d_fk_usuarios_id` (`autor_id`),
  ADD KEY `governanca_comentari_resposta_a_id_7ebc3c8c_fk_governanc` (`resposta_a_id`);

--
-- Índices para tabela `governanca_consultas_publicas`
--
ALTER TABLE `governanca_consultas_publicas`
  ADD PRIMARY KEY (`id`),
  ADD KEY `governanca_consultas_criado_por_id_7113236e_fk_usuarios_` (`criado_por_id`),
  ADD KEY `governanca_consultas_publicas_status_e2f3e13f` (`status`);

--
-- Índices para tabela `governanca_convocatorias`
--
ALTER TABLE `governanca_convocatorias`
  ADD PRIMARY KEY (`id`),
  ADD KEY `governanca_convocatorias_assembleia_id_b9ad71e9` (`assembleia_id`),
  ADD KEY `governanca_convocatorias_status_134aa807` (`status`);

--
-- Índices para tabela `governanca_documentos`
--
ALTER TABLE `governanca_documentos`
  ADD PRIMARY KEY (`id`),
  ADD KEY `governanca_documentos_created_by_id_b22c96d6_fk_usuarios_id` (`created_by_id`),
  ADD KEY `governanca_documentos_assembleia_id_e39f80bb` (`assembleia_id`),
  ADD KEY `governanca_documentos_publicado_9c3247f1` (`publicado`);

--
-- Índices para tabela `governanca_estado_financeiro`
--
ALTER TABLE `governanca_estado_financeiro`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `despachante_id` (`despachante_id`),
  ADD KEY `governanca_estado_financeiro_estado_be2860e6` (`estado`);

--
-- Índices para tabela `governanca_historico_quotas`
--
ALTER TABLE `governanca_historico_quotas`
  ADD PRIMARY KEY (`id`),
  ADD KEY `governanca_historico_pagamento_id_0efba195_fk_governanc` (`pagamento_id`),
  ADD KEY `governanca_historico_utilizador_id_bf0b78c0_fk_usuarios_` (`utilizador_id`),
  ADD KEY `governanca_historico_quotas_acao_1bf7994e` (`acao`),
  ADD KEY `governanca_historico_quotas_created_at_a77fe837` (`created_at`),
  ADD KEY `governanca__membro__778f35_idx` (`membro_id`,`created_at`),
  ADD KEY `governanca__quota_i_9bcc3a_idx` (`quota_id`,`created_at`);

--
-- Índices para tabela `governanca_isencoes_membro`
--
ALTER TABLE `governanca_isencoes_membro`
  ADD PRIMARY KEY (`id`),
  ADD KEY `governanca_isencoes__aprovado_por_id_e3bdbb16_fk_usuarios_` (`aprovado_por_id`),
  ADD KEY `governanca_isencoes__despachante_id_950ed708_fk_usuarios_` (`despachante_id`),
  ADD KEY `governanca_isencoes__tipo_quota_id_2ce82c94_fk_governanc` (`tipo_quota_id`);

--
-- Índices para tabela `governanca_logs_assembleia`
--
ALTER TABLE `governanca_logs_assembleia`
  ADD PRIMARY KEY (`id`),
  ADD KEY `governanca_logs_assembleia_usuario_id_419f2618_fk_usuarios_id` (`usuario_id`),
  ADD KEY `governanca__assembl_514adf_idx` (`assembleia_id`,`created_at`);

--
-- Índices para tabela `governanca_manifestos`
--
ALTER TABLE `governanca_manifestos`
  ADD PRIMARY KEY (`id`),
  ADD KEY `governanca_manifesto_assembleia_id_9426a0c5_fk_governanc` (`assembleia_id`),
  ADD KEY `governanca_manifestos_gerado_por_id_b6e7d933_fk_usuarios_id` (`gerado_por_id`);

--
-- Índices para tabela `governanca_mesa`
--
ALTER TABLE `governanca_mesa`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `governanca_mesa_assembleia_id_usuario_id_44f115ae_uniq` (`assembleia_id`,`usuario_id`),
  ADD KEY `governanca_mesa_usuario_id_f7cd229b_fk_usuarios_id` (`usuario_id`);

--
-- Índices para tabela `governanca_notificacoes`
--
ALTER TABLE `governanca_notificacoes`
  ADD PRIMARY KEY (`id`),
  ADD KEY `governanca_notificacoes_usuario_id_48c37a74` (`usuario_id`),
  ADD KEY `governanca_notificacoes_lida_03bdd9c3` (`lida`),
  ADD KEY `governanca_notificacoes_tipo_5ae484b8` (`tipo`);

--
-- Índices para tabela `governanca_pagamentos_quota`
--
ALTER TABLE `governanca_pagamentos_quota`
  ADD PRIMARY KEY (`id`),
  ADD KEY `governanca_pagamento_confirmado_por_id_adaa5a65_fk_usuarios_` (`confirmado_por_id`),
  ADD KEY `governanca_pagamentos_quota_quota_id_7005e5fc` (`quota_id`),
  ADD KEY `governanca_pagamentos_quota_despachante_id_668f0286` (`despachante_id`),
  ADD KEY `governanca_pagamentos_quota_status_9381c866` (`status`);

--
-- Índices para tabela `governanca_pautas`
--
ALTER TABLE `governanca_pautas`
  ADD PRIMARY KEY (`id`),
  ADD KEY `governanca_pautas_assembleia_id_36b3e410` (`assembleia_id`),
  ADD KEY `governanca_pautas_status_626bfabf` (`status`);

--
-- Índices para tabela `governanca_presencas`
--
ALTER TABLE `governanca_presencas`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `governanca_presencas_assembleia_id_usuario_id_b40467a4_uniq` (`assembleia_id`,`usuario_id`),
  ADD KEY `governanca_presencas_usuario_id_d6030ca0_fk_usuarios_id` (`usuario_id`);

--
-- Índices para tabela `governanca_procuracao`
--
ALTER TABLE `governanca_procuracao`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `governanca_procuracao_assembleia_id_outorgante_id_1f47bdb1_uniq` (`assembleia_id`,`outorgante_id`),
  ADD KEY `governanca_procuracao_outorgante_id_5027fa85` (`outorgante_id`),
  ADD KEY `governanca_procuracao_outorgado_id_765fdc84` (`outorgado_id`),
  ADD KEY `governanca_procuracao_status_076accac` (`status`);

--
-- Índices para tabela `governanca_quotas_geradas`
--
ALTER TABLE `governanca_quotas_geradas`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `fatura_uuid` (`fatura_uuid`),
  ADD UNIQUE KEY `referencia` (`referencia`),
  ADD KEY `governanca_quotas_geradas_despachante_id_3c25d395` (`despachante_id`),
  ADD KEY `governanca_quotas_ge_tipo_id_6cd9bd1c_fk_governanc` (`tipo_id`),
  ADD KEY `governanca_quotas_geradas_ano_677a7973` (`ano`),
  ADD KEY `governanca_quotas_geradas_mes_ed5b2995` (`mes`),
  ADD KEY `governanca_quotas_geradas_status_21c849e8` (`status`);

--
-- Índices para tabela `governanca_quota_config`
--
ALTER TABLE `governanca_quota_config`
  ADD PRIMARY KEY (`id`),
  ADD KEY `governanca_quota_con_categoria_id_6d766c05_fk_governanc` (`categoria_id`),
  ADD KEY `governanca_quota_con_tipo_id_121bedb8_fk_governanc` (`tipo_id`);

--
-- Índices para tabela `governanca_recibos_voto`
--
ALTER TABLE `governanca_recibos_voto`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `recibo_hash` (`recibo_hash`),
  ADD UNIQUE KEY `voto_id` (`voto_id`);

--
-- Índices para tabela `governanca_relatorios_consulta`
--
ALTER TABLE `governanca_relatorios_consulta`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `consulta_id` (`consulta_id`),
  ADD KEY `governanca_relatorio_criado_por_id_d8db590c_fk_usuarios_` (`criado_por_id`);

--
-- Índices para tabela `governanca_respostas_presenca`
--
ALTER TABLE `governanca_respostas_presenca`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `governanca_respostas_pre_assembleia_id_usuario_id_2b9d6df1_uniq` (`assembleia_id`,`usuario_id`),
  ADD KEY `governanca_respostas_presenca_usuario_id_00c7529b_fk_usuarios_id` (`usuario_id`);

--
-- Índices para tabela `governanca_tipos_quota`
--
ALTER TABLE `governanca_tipos_quota`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `slug` (`slug`);

--
-- Índices para tabela `governanca_votacoes_consulta`
--
ALTER TABLE `governanca_votacoes_consulta`
  ADD PRIMARY KEY (`id`),
  ADD KEY `governanca_votacoes_consulta_consulta_id_1c751528` (`consulta_id`);

--
-- Índices para tabela `governanca_votos`
--
ALTER TABLE `governanca_votos`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `governanca_votos_pauta_id_usuario_id_em_d_c3cb5591_uniq` (`pauta_id`,`usuario_id`,`em_delegacao`,`delegado_de_id`),
  ADD KEY `governanca_votos_delegado_de_id_d5f96332_fk_usuarios_id` (`delegado_de_id`),
  ADD KEY `governanca_votos_usuario_id_3ec84d05_fk_usuarios_id` (`usuario_id`),
  ADD KEY `governanca_votos_pauta_id_b699860e` (`pauta_id`);

--
-- Índices para tabela `governanca_votos_consulta`
--
ALTER TABLE `governanca_votos_consulta`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `governanca_votos_consulta_votacao_id_usuario_id_c7d51a18_uniq` (`votacao_id`,`usuario_id`),
  ADD KEY `governanca_votos_consulta_usuario_id_bb73438b_fk_usuarios_id` (`usuario_id`);

--
-- Índices para tabela `permissoes`
--
ALTER TABLE `permissoes`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `codigo` (`codigo`);

--
-- Índices para tabela `permissoes_cargo`
--
ALTER TABLE `permissoes_cargo`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `codigo` (`codigo`);

--
-- Índices para tabela `rh_avaliacoes`
--
ALTER TABLE `rh_avaliacoes`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `rh_avaliacoes_ciclo_id_colaborador_id_868e5cec_uniq` (`ciclo_id`,`colaborador_id`),
  ADD KEY `rh_avaliacoes_colaborador_id_9a8147fb_fk_rh_colaboradores_id` (`colaborador_id`);

--
-- Índices para tabela `rh_candidaturas`
--
ALTER TABLE `rh_candidaturas`
  ADD PRIMARY KEY (`id`),
  ADD KEY `rh_candidat_vaga_id_c9c0d6_idx` (`vaga_id`),
  ADD KEY `rh_candidat_estado_810cc6_idx` (`estado`),
  ADD KEY `rh_candidat_vaga_id_f0a429_idx` (`vaga_id`,`estado`),
  ADD KEY `rh_candidat_criado__479960_idx` (`criado_em`);

--
-- Índices para tabela `rh_cargos_mesa`
--
ALTER TABLE `rh_cargos_mesa`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `funcao` (`funcao`),
  ADD UNIQUE KEY `usuario_id` (`usuario_id`);

--
-- Índices para tabela `rh_ciclos_avaliacao`
--
ALTER TABLE `rh_ciclos_avaliacao`
  ADD PRIMARY KEY (`id`),
  ADD KEY `rh_ciclos_avaliacao_banca_id_7f2379b6` (`banca_id`);

--
-- Índices para tabela `rh_colaboradores`
--
ALTER TABLE `rh_colaboradores`
  ADD PRIMARY KEY (`id`),
  ADD KEY `rh_colabora_banca_i_4d583d_idx` (`banca_id`),
  ADD KEY `rh_colabora_filial__8dfc92_idx` (`filial_id`),
  ADD KEY `rh_colabora_estado_fc2622_idx` (`estado`),
  ADD KEY `rh_colabora_usuario_97bc52_idx` (`usuario_id`),
  ADD KEY `rh_colabora_banca_i_2ac326_idx` (`banca_id`,`filial_id`),
  ADD KEY `rh_colabora_criado__a010c0_idx` (`criado_em`);

--
-- Índices para tabela `rh_colaborador_documentos`
--
ALTER TABLE `rh_colaborador_documentos`
  ADD PRIMARY KEY (`id`),
  ADD KEY `rh_colaborador_documentos_colaborador_id_53fccf23` (`colaborador_id`);

--
-- Índices para tabela `rh_empresas`
--
ALTER TABLE `rh_empresas`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `nif` (`nif`),
  ADD KEY `rh_empresas_usuario_8a2f5d_idx` (`usuario_id`),
  ADD KEY `rh_empresas_ativa_119907_idx` (`ativa`),
  ADD KEY `rh_empresas_nif_f3dd04_idx` (`nif`);

--
-- Índices para tabela `rh_entrevistas`
--
ALTER TABLE `rh_entrevistas`
  ADD PRIMARY KEY (`id`),
  ADD KEY `rh_entrevistas_candidatura_id_01e3930d` (`candidatura_id`);

--
-- Índices para tabela `rh_faturas`
--
ALTER TABLE `rh_faturas`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `codigo` (`codigo`),
  ADD KEY `rh_faturas_colaborador_id_5ad58f11_fk_rh_colaboradores_id` (`colaborador_id`),
  ADD KEY `rh_faturas_processamento_salari_c5d2ad0b_fk_rh_proces` (`processamento_salarial_id`),
  ADD KEY `rh_faturas_banca_id_b7549d23` (`banca_id`);

--
-- Índices para tabela `rh_filiais`
--
ALTER TABLE `rh_filiais`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `rh_filiais_banca_id_provincia_75b7ecae_uniq` (`banca_id`,`provincia`),
  ADD KEY `rh_filiais_banca_i_77607a_idx` (`banca_id`,`ativa`),
  ADD KEY `rh_filiais_provinc_521b1e_idx` (`provincia`);

--
-- Índices para tabela `rh_gestores_filial`
--
ALTER TABLE `rh_gestores_filial`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `colaborador_id` (`colaborador_id`),
  ADD UNIQUE KEY `rh_gestores_filial_colaborador_id_filial_id_177c8ceb_uniq` (`colaborador_id`,`filial_id`),
  ADD KEY `rh_gestores_colabor_aa6dbf_idx` (`colaborador_id`,`ativo`),
  ADD KEY `rh_gestores_filial__b72f52_idx` (`filial_id`,`ativo`);

--
-- Índices para tabela `rh_metricas_avaliacao`
--
ALTER TABLE `rh_metricas_avaliacao`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `rh_metricas_avaliacao_ciclo_id_nome_79de7dfc_uniq` (`ciclo_id`,`nome`);

--
-- Índices para tabela `rh_notas_metricas`
--
ALTER TABLE `rh_notas_metricas`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `rh_notas_metricas_avaliacao_id_metrica_id_82e6f073_uniq` (`avaliacao_id`,`metrica_id`),
  ADD KEY `rh_notas_metricas_metrica_id_0d6f639d_fk_rh_metric` (`metrica_id`);

--
-- Índices para tabela `rh_pedidos_ferias`
--
ALTER TABLE `rh_pedidos_ferias`
  ADD PRIMARY KEY (`id`),
  ADD KEY `rh_pedidos_ferias_colaborador_id_5c59ebb5` (`colaborador_id`);

--
-- Índices para tabela `rh_planos_integracao`
--
ALTER TABLE `rh_planos_integracao`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `candidatura_id` (`candidatura_id`),
  ADD KEY `rh_planos_integracao_colaborador_id_1d0e7824` (`colaborador_id`);

--
-- Índices para tabela `rh_presencas`
--
ALTER TABLE `rh_presencas`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `rh_presencas_colaborador_id_data_74c6f9e4_uniq` (`colaborador_id`,`data`),
  ADD KEY `rh_presencas_aprovado_por_id_9870d01e_fk_rh_colaboradores_id` (`aprovado_por_id`);

--
-- Índices para tabela `rh_processamentos`
--
ALTER TABLE `rh_processamentos`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `rh_processamentos_banca_id_mes_ano_0ebd7e0f_uniq` (`banca_id`,`mes`,`ano`);

--
-- Índices para tabela `rh_recibos`
--
ALTER TABLE `rh_recibos`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `rh_recibos_processamento_id_colaborador_id_f4f9ca6f_uniq` (`processamento_id`,`colaborador_id`),
  ADD KEY `rh_recibos_colaborador_id_e93023ee_fk_rh_colaboradores_id` (`colaborador_id`);

--
-- Índices para tabela `rh_recibo_subsidios`
--
ALTER TABLE `rh_recibo_subsidios`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `rh_recibo_subsidios_recibo_id_subsidio_id_f5b8dc0b_uniq` (`recibo_id`,`subsidio_id`),
  ADD KEY `rh_recibo_subsidios_subsidio_id_42bd3ca0_fk_rh_subsidios_id` (`subsidio_id`);

--
-- Índices para tabela `rh_subsidios`
--
ALTER TABLE `rh_subsidios`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `rh_subsidios_banca_id_codigo_bb83cc6f_uniq` (`banca_id`,`codigo`);

--
-- Índices para tabela `rh_subsidios_colaboradores_especificos`
--
ALTER TABLE `rh_subsidios_colaboradores_especificos`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `rh_subsidios_colaborador_subsidio_id_colaborador__2bfc19cf_uniq` (`subsidio_id`,`colaborador_id`),
  ADD KEY `rh_subsidios_colabor_colaborador_id_9883e0b3_fk_rh_colabo` (`colaborador_id`);

--
-- Índices para tabela `rh_tarefas_integracao`
--
ALTER TABLE `rh_tarefas_integracao`
  ADD PRIMARY KEY (`id`),
  ADD KEY `rh_tarefas_integracao_plano_id_5cec0637` (`plano_id`);

--
-- Índices para tabela `rh_vagas`
--
ALTER TABLE `rh_vagas`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `link_externo` (`link_externo`),
  ADD KEY `rh_vagas_banca_i_fba620_idx` (`banca_id`),
  ADD KEY `rh_vagas_filial__9dd631_idx` (`filial_id`),
  ADD KEY `rh_vagas_estado_243e15_idx` (`estado`),
  ADD KEY `rh_vagas_banca_i_67f9f6_idx` (`banca_id`,`estado`),
  ADD KEY `rh_vagas_criado__dd04ee_idx` (`criado_em`);

--
-- Índices para tabela `usuarios`
--
ALTER TABLE `usuarios`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `username` (`username`),
  ADD UNIQUE KEY `email` (`email`),
  ADD KEY `usuarios_categoria_id_a38b1748_fk_governanc` (`categoria_id`),
  ADD KEY `usuarios_papel_7b266fcd` (`papel`),
  ADD KEY `usuarios_status_4b3cec99` (`status`),
  ADD KEY `idx_usuario_papel_status` (`papel`,`status`),
  ADD KEY `usuarios_nome_d429eb95` (`nome`);

--
-- Índices para tabela `usuarios_cargos`
--
ALTER TABLE `usuarios_cargos`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `usuarios_cargos_cargo_id_9c79f074_uniq` (`cargo_id`),
  ADD KEY `usuarios_cargos_atribuido_por_id_3580ad62_fk_usuarios_id` (`atribuido_por_id`),
  ADD KEY `usuarios_cargos_usuario_id_d3f97be5` (`usuario_id`);

--
-- AUTO_INCREMENT de tabelas despejadas
--

--
-- AUTO_INCREMENT de tabela `auth_group`
--
ALTER TABLE `auth_group`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `auth_group_permissions`
--
ALTER TABLE `auth_group_permissions`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `auth_permission`
--
ALTER TABLE `auth_permission`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=153;

--
-- AUTO_INCREMENT de tabela `auth_user`
--
ALTER TABLE `auth_user`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `auth_user_groups`
--
ALTER TABLE `auth_user_groups`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `auth_user_user_permissions`
--
ALTER TABLE `auth_user_user_permissions`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `cargos`
--
ALTER TABLE `cargos`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=2;

--
-- AUTO_INCREMENT de tabela `cargos_permissoes`
--
ALTER TABLE `cargos_permissoes`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `clientes_clientes`
--
ALTER TABLE `clientes_clientes`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=5;

--
-- AUTO_INCREMENT de tabela `declaracoes_unicas`
--
ALTER TABLE `declaracoes_unicas`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=4;

--
-- AUTO_INCREMENT de tabela `django_admin_log`
--
ALTER TABLE `django_admin_log`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `django_apscheduler_djangojobexecution`
--
ALTER TABLE `django_apscheduler_djangojobexecution`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `django_content_type`
--
ALTER TABLE `django_content_type`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=39;

--
-- AUTO_INCREMENT de tabela `django_migrations`
--
ALTER TABLE `django_migrations`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=57;

--
-- AUTO_INCREMENT de tabela `governanca_artigos_documento`
--
ALTER TABLE `governanca_artigos_documento`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `governanca_assembleias`
--
ALTER TABLE `governanca_assembleias`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `governanca_atas`
--
ALTER TABLE `governanca_atas`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `governanca_carteiras_profissionais`
--
ALTER TABLE `governanca_carteiras_profissionais`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `governanca_categorias_membro`
--
ALTER TABLE `governanca_categorias_membro`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `governanca_certidoes_regularidade`
--
ALTER TABLE `governanca_certidoes_regularidade`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `governanca_chat`
--
ALTER TABLE `governanca_chat`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `governanca_comentarios_consulta`
--
ALTER TABLE `governanca_comentarios_consulta`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `governanca_consultas_publicas`
--
ALTER TABLE `governanca_consultas_publicas`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `governanca_convocatorias`
--
ALTER TABLE `governanca_convocatorias`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `governanca_documentos`
--
ALTER TABLE `governanca_documentos`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `governanca_estado_financeiro`
--
ALTER TABLE `governanca_estado_financeiro`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=4;

--
-- AUTO_INCREMENT de tabela `governanca_historico_quotas`
--
ALTER TABLE `governanca_historico_quotas`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `governanca_isencoes_membro`
--
ALTER TABLE `governanca_isencoes_membro`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `governanca_logs_assembleia`
--
ALTER TABLE `governanca_logs_assembleia`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `governanca_manifestos`
--
ALTER TABLE `governanca_manifestos`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `governanca_mesa`
--
ALTER TABLE `governanca_mesa`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `governanca_notificacoes`
--
ALTER TABLE `governanca_notificacoes`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `governanca_pagamentos_quota`
--
ALTER TABLE `governanca_pagamentos_quota`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `governanca_pautas`
--
ALTER TABLE `governanca_pautas`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `governanca_presencas`
--
ALTER TABLE `governanca_presencas`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `governanca_procuracao`
--
ALTER TABLE `governanca_procuracao`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `governanca_quotas_geradas`
--
ALTER TABLE `governanca_quotas_geradas`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `governanca_quota_config`
--
ALTER TABLE `governanca_quota_config`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `governanca_recibos_voto`
--
ALTER TABLE `governanca_recibos_voto`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `governanca_relatorios_consulta`
--
ALTER TABLE `governanca_relatorios_consulta`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `governanca_respostas_presenca`
--
ALTER TABLE `governanca_respostas_presenca`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `governanca_tipos_quota`
--
ALTER TABLE `governanca_tipos_quota`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `governanca_votacoes_consulta`
--
ALTER TABLE `governanca_votacoes_consulta`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `governanca_votos`
--
ALTER TABLE `governanca_votos`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `governanca_votos_consulta`
--
ALTER TABLE `governanca_votos_consulta`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `permissoes`
--
ALTER TABLE `permissoes`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `permissoes_cargo`
--
ALTER TABLE `permissoes_cargo`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=6;

--
-- AUTO_INCREMENT de tabela `rh_avaliacoes`
--
ALTER TABLE `rh_avaliacoes`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `rh_candidaturas`
--
ALTER TABLE `rh_candidaturas`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `rh_cargos_mesa`
--
ALTER TABLE `rh_cargos_mesa`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `rh_ciclos_avaliacao`
--
ALTER TABLE `rh_ciclos_avaliacao`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `rh_colaboradores`
--
ALTER TABLE `rh_colaboradores`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `rh_colaborador_documentos`
--
ALTER TABLE `rh_colaborador_documentos`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `rh_empresas`
--
ALTER TABLE `rh_empresas`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `rh_entrevistas`
--
ALTER TABLE `rh_entrevistas`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `rh_faturas`
--
ALTER TABLE `rh_faturas`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `rh_filiais`
--
ALTER TABLE `rh_filiais`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `rh_gestores_filial`
--
ALTER TABLE `rh_gestores_filial`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `rh_metricas_avaliacao`
--
ALTER TABLE `rh_metricas_avaliacao`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `rh_notas_metricas`
--
ALTER TABLE `rh_notas_metricas`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `rh_pedidos_ferias`
--
ALTER TABLE `rh_pedidos_ferias`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `rh_planos_integracao`
--
ALTER TABLE `rh_planos_integracao`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `rh_presencas`
--
ALTER TABLE `rh_presencas`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `rh_processamentos`
--
ALTER TABLE `rh_processamentos`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `rh_recibos`
--
ALTER TABLE `rh_recibos`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `rh_recibo_subsidios`
--
ALTER TABLE `rh_recibo_subsidios`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `rh_subsidios`
--
ALTER TABLE `rh_subsidios`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `rh_subsidios_colaboradores_especificos`
--
ALTER TABLE `rh_subsidios_colaboradores_especificos`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `rh_tarefas_integracao`
--
ALTER TABLE `rh_tarefas_integracao`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `rh_vagas`
--
ALTER TABLE `rh_vagas`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de tabela `usuarios`
--
ALTER TABLE `usuarios`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=7;

--
-- AUTO_INCREMENT de tabela `usuarios_cargos`
--
ALTER TABLE `usuarios_cargos`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- Restrições para despejos de tabelas
--

--
-- Limitadores para a tabela `auth_group_permissions`
--
ALTER TABLE `auth_group_permissions`
  ADD CONSTRAINT `auth_group_permissio_permission_id_84c5c92e_fk_auth_perm` FOREIGN KEY (`permission_id`) REFERENCES `auth_permission` (`id`),
  ADD CONSTRAINT `auth_group_permissions_group_id_b120cbf9_fk_auth_group_id` FOREIGN KEY (`group_id`) REFERENCES `auth_group` (`id`);

--
-- Limitadores para a tabela `auth_permission`
--
ALTER TABLE `auth_permission`
  ADD CONSTRAINT `auth_permission_content_type_id_2f476e4b_fk_django_co` FOREIGN KEY (`content_type_id`) REFERENCES `django_content_type` (`id`);

--
-- Limitadores para a tabela `auth_user_groups`
--
ALTER TABLE `auth_user_groups`
  ADD CONSTRAINT `auth_user_groups_group_id_97559544_fk_auth_group_id` FOREIGN KEY (`group_id`) REFERENCES `auth_group` (`id`),
  ADD CONSTRAINT `auth_user_groups_user_id_6a12ed8b_fk_auth_user_id` FOREIGN KEY (`user_id`) REFERENCES `auth_user` (`id`);

--
-- Limitadores para a tabela `auth_user_user_permissions`
--
ALTER TABLE `auth_user_user_permissions`
  ADD CONSTRAINT `auth_user_user_permi_permission_id_1fbb5f2c_fk_auth_perm` FOREIGN KEY (`permission_id`) REFERENCES `auth_permission` (`id`),
  ADD CONSTRAINT `auth_user_user_permissions_user_id_a95ead1b_fk_auth_user_id` FOREIGN KEY (`user_id`) REFERENCES `auth_user` (`id`);

--
-- Limitadores para a tabela `cargos_permissoes`
--
ALTER TABLE `cargos_permissoes`
  ADD CONSTRAINT `cargos_permissoes_cargo_id_a60ba049_fk_cargos_id` FOREIGN KEY (`cargo_id`) REFERENCES `cargos` (`id`),
  ADD CONSTRAINT `cargos_permissoes_permissao_id_d6ba7a05_fk_permissoes_id` FOREIGN KEY (`permissao_id`) REFERENCES `permissoes` (`id`);

--
-- Limitadores para a tabela `django_admin_log`
--
ALTER TABLE `django_admin_log`
  ADD CONSTRAINT `django_admin_log_content_type_id_c4bce8eb_fk_django_co` FOREIGN KEY (`content_type_id`) REFERENCES `django_content_type` (`id`),
  ADD CONSTRAINT `django_admin_log_user_id_c564eba6_fk_auth_user_id` FOREIGN KEY (`user_id`) REFERENCES `auth_user` (`id`);

--
-- Limitadores para a tabela `django_apscheduler_djangojobexecution`
--
ALTER TABLE `django_apscheduler_djangojobexecution`
  ADD CONSTRAINT `django_apscheduler_djangojobexecution_job_id_daf5090a_fk` FOREIGN KEY (`job_id`) REFERENCES `django_apscheduler_djangojob` (`id`);

--
-- Limitadores para a tabela `governanca_artigos_documento`
--
ALTER TABLE `governanca_artigos_documento`
  ADD CONSTRAINT `governanca_artigos_d_consulta_id_cf6ce67f_fk_governanc` FOREIGN KEY (`consulta_id`) REFERENCES `governanca_consultas_publicas` (`id`);

--
-- Limitadores para a tabela `governanca_assembleias`
--
ALTER TABLE `governanca_assembleias`
  ADD CONSTRAINT `governanca_assembleias_created_by_id_e7c7ac68_fk_usuarios_id` FOREIGN KEY (`created_by_id`) REFERENCES `usuarios` (`id`);

--
-- Limitadores para a tabela `governanca_atas`
--
ALTER TABLE `governanca_atas`
  ADD CONSTRAINT `governanca_atas_assembleia_id_23d2d6de_fk_governanc` FOREIGN KEY (`assembleia_id`) REFERENCES `governanca_assembleias` (`id`),
  ADD CONSTRAINT `governanca_atas_assinado_por_id_6b67f54b_fk_usuarios_id` FOREIGN KEY (`assinado_por_id`) REFERENCES `usuarios` (`id`);

--
-- Limitadores para a tabela `governanca_carteiras_profissionais`
--
ALTER TABLE `governanca_carteiras_profissionais`
  ADD CONSTRAINT `governanca_carteiras_despachante_id_dec6a43e_fk_usuarios_` FOREIGN KEY (`despachante_id`) REFERENCES `usuarios` (`id`);

--
-- Limitadores para a tabela `governanca_certidoes_regularidade`
--
ALTER TABLE `governanca_certidoes_regularidade`
  ADD CONSTRAINT `governanca_certidoes_despachante_id_1f3d5736_fk_usuarios_` FOREIGN KEY (`despachante_id`) REFERENCES `usuarios` (`id`),
  ADD CONSTRAINT `governanca_certidoes_emitido_por_id_e52ff186_fk_usuarios_` FOREIGN KEY (`emitido_por_id`) REFERENCES `usuarios` (`id`);

--
-- Limitadores para a tabela `governanca_chat`
--
ALTER TABLE `governanca_chat`
  ADD CONSTRAINT `governanca_chat_assembleia_id_29ffc0f9_fk_governanc` FOREIGN KEY (`assembleia_id`) REFERENCES `governanca_assembleias` (`id`),
  ADD CONSTRAINT `governanca_chat_usuario_id_280934ab_fk_usuarios_id` FOREIGN KEY (`usuario_id`) REFERENCES `usuarios` (`id`);

--
-- Limitadores para a tabela `governanca_comentarios_consulta`
--
ALTER TABLE `governanca_comentarios_consulta`
  ADD CONSTRAINT `governanca_comentari_artigo_id_6390452b_fk_governanc` FOREIGN KEY (`artigo_id`) REFERENCES `governanca_artigos_documento` (`id`),
  ADD CONSTRAINT `governanca_comentari_resposta_a_id_7ebc3c8c_fk_governanc` FOREIGN KEY (`resposta_a_id`) REFERENCES `governanca_comentarios_consulta` (`id`),
  ADD CONSTRAINT `governanca_comentarios_consulta_autor_id_3e436a4d_fk_usuarios_id` FOREIGN KEY (`autor_id`) REFERENCES `usuarios` (`id`);

--
-- Limitadores para a tabela `governanca_consultas_publicas`
--
ALTER TABLE `governanca_consultas_publicas`
  ADD CONSTRAINT `governanca_consultas_criado_por_id_7113236e_fk_usuarios_` FOREIGN KEY (`criado_por_id`) REFERENCES `usuarios` (`id`);

--
-- Limitadores para a tabela `governanca_convocatorias`
--
ALTER TABLE `governanca_convocatorias`
  ADD CONSTRAINT `governanca_convocato_assembleia_id_b9ad71e9_fk_governanc` FOREIGN KEY (`assembleia_id`) REFERENCES `governanca_assembleias` (`id`);

--
-- Limitadores para a tabela `governanca_documentos`
--
ALTER TABLE `governanca_documentos`
  ADD CONSTRAINT `governanca_documento_assembleia_id_e39f80bb_fk_governanc` FOREIGN KEY (`assembleia_id`) REFERENCES `governanca_assembleias` (`id`),
  ADD CONSTRAINT `governanca_documentos_created_by_id_b22c96d6_fk_usuarios_id` FOREIGN KEY (`created_by_id`) REFERENCES `usuarios` (`id`);

--
-- Limitadores para a tabela `governanca_estado_financeiro`
--
ALTER TABLE `governanca_estado_financeiro`
  ADD CONSTRAINT `governanca_estado_fi_despachante_id_3ab1d983_fk_usuarios_` FOREIGN KEY (`despachante_id`) REFERENCES `usuarios` (`id`);

--
-- Limitadores para a tabela `governanca_historico_quotas`
--
ALTER TABLE `governanca_historico_quotas`
  ADD CONSTRAINT `governanca_historico_pagamento_id_0efba195_fk_governanc` FOREIGN KEY (`pagamento_id`) REFERENCES `governanca_pagamentos_quota` (`id`),
  ADD CONSTRAINT `governanca_historico_quota_id_6a53fcf7_fk_governanc` FOREIGN KEY (`quota_id`) REFERENCES `governanca_quotas_geradas` (`id`),
  ADD CONSTRAINT `governanca_historico_quotas_membro_id_a969bd99_fk_usuarios_id` FOREIGN KEY (`membro_id`) REFERENCES `usuarios` (`id`),
  ADD CONSTRAINT `governanca_historico_utilizador_id_bf0b78c0_fk_usuarios_` FOREIGN KEY (`utilizador_id`) REFERENCES `usuarios` (`id`);

--
-- Limitadores para a tabela `governanca_isencoes_membro`
--
ALTER TABLE `governanca_isencoes_membro`
  ADD CONSTRAINT `governanca_isencoes__aprovado_por_id_e3bdbb16_fk_usuarios_` FOREIGN KEY (`aprovado_por_id`) REFERENCES `usuarios` (`id`),
  ADD CONSTRAINT `governanca_isencoes__despachante_id_950ed708_fk_usuarios_` FOREIGN KEY (`despachante_id`) REFERENCES `usuarios` (`id`),
  ADD CONSTRAINT `governanca_isencoes__tipo_quota_id_2ce82c94_fk_governanc` FOREIGN KEY (`tipo_quota_id`) REFERENCES `governanca_tipos_quota` (`id`);

--
-- Limitadores para a tabela `governanca_logs_assembleia`
--
ALTER TABLE `governanca_logs_assembleia`
  ADD CONSTRAINT `governanca_logs_asse_assembleia_id_dadd69fc_fk_governanc` FOREIGN KEY (`assembleia_id`) REFERENCES `governanca_assembleias` (`id`),
  ADD CONSTRAINT `governanca_logs_assembleia_usuario_id_419f2618_fk_usuarios_id` FOREIGN KEY (`usuario_id`) REFERENCES `usuarios` (`id`);

--
-- Limitadores para a tabela `governanca_manifestos`
--
ALTER TABLE `governanca_manifestos`
  ADD CONSTRAINT `governanca_manifesto_assembleia_id_9426a0c5_fk_governanc` FOREIGN KEY (`assembleia_id`) REFERENCES `governanca_assembleias` (`id`),
  ADD CONSTRAINT `governanca_manifestos_gerado_por_id_b6e7d933_fk_usuarios_id` FOREIGN KEY (`gerado_por_id`) REFERENCES `usuarios` (`id`);

--
-- Limitadores para a tabela `governanca_mesa`
--
ALTER TABLE `governanca_mesa`
  ADD CONSTRAINT `governanca_mesa_assembleia_id_e2049ccc_fk_governanc` FOREIGN KEY (`assembleia_id`) REFERENCES `governanca_assembleias` (`id`),
  ADD CONSTRAINT `governanca_mesa_usuario_id_f7cd229b_fk_usuarios_id` FOREIGN KEY (`usuario_id`) REFERENCES `usuarios` (`id`);

--
-- Limitadores para a tabela `governanca_notificacoes`
--
ALTER TABLE `governanca_notificacoes`
  ADD CONSTRAINT `governanca_notificacoes_usuario_id_48c37a74_fk_usuarios_id` FOREIGN KEY (`usuario_id`) REFERENCES `usuarios` (`id`);

--
-- Limitadores para a tabela `governanca_pagamentos_quota`
--
ALTER TABLE `governanca_pagamentos_quota`
  ADD CONSTRAINT `governanca_pagamento_confirmado_por_id_adaa5a65_fk_usuarios_` FOREIGN KEY (`confirmado_por_id`) REFERENCES `usuarios` (`id`),
  ADD CONSTRAINT `governanca_pagamento_despachante_id_668f0286_fk_usuarios_` FOREIGN KEY (`despachante_id`) REFERENCES `usuarios` (`id`),
  ADD CONSTRAINT `governanca_pagamento_quota_id_7005e5fc_fk_governanc` FOREIGN KEY (`quota_id`) REFERENCES `governanca_quotas_geradas` (`id`);

--
-- Limitadores para a tabela `governanca_pautas`
--
ALTER TABLE `governanca_pautas`
  ADD CONSTRAINT `governanca_pautas_assembleia_id_36b3e410_fk_governanc` FOREIGN KEY (`assembleia_id`) REFERENCES `governanca_assembleias` (`id`);

--
-- Limitadores para a tabela `governanca_presencas`
--
ALTER TABLE `governanca_presencas`
  ADD CONSTRAINT `governanca_presencas_assembleia_id_fde305f5_fk_governanc` FOREIGN KEY (`assembleia_id`) REFERENCES `governanca_assembleias` (`id`),
  ADD CONSTRAINT `governanca_presencas_usuario_id_d6030ca0_fk_usuarios_id` FOREIGN KEY (`usuario_id`) REFERENCES `usuarios` (`id`);

--
-- Limitadores para a tabela `governanca_procuracao`
--
ALTER TABLE `governanca_procuracao`
  ADD CONSTRAINT `governanca_procuraca_assembleia_id_f5cc9fe8_fk_governanc` FOREIGN KEY (`assembleia_id`) REFERENCES `governanca_assembleias` (`id`),
  ADD CONSTRAINT `governanca_procuracao_outorgado_id_765fdc84_fk_usuarios_id` FOREIGN KEY (`outorgado_id`) REFERENCES `usuarios` (`id`),
  ADD CONSTRAINT `governanca_procuracao_outorgante_id_5027fa85_fk_usuarios_id` FOREIGN KEY (`outorgante_id`) REFERENCES `usuarios` (`id`);

--
-- Limitadores para a tabela `governanca_quotas_geradas`
--
ALTER TABLE `governanca_quotas_geradas`
  ADD CONSTRAINT `governanca_quotas_ge_tipo_id_6cd9bd1c_fk_governanc` FOREIGN KEY (`tipo_id`) REFERENCES `governanca_tipos_quota` (`id`),
  ADD CONSTRAINT `governanca_quotas_geradas_despachante_id_3c25d395_fk_usuarios_id` FOREIGN KEY (`despachante_id`) REFERENCES `usuarios` (`id`);

--
-- Limitadores para a tabela `governanca_quota_config`
--
ALTER TABLE `governanca_quota_config`
  ADD CONSTRAINT `governanca_quota_con_categoria_id_6d766c05_fk_governanc` FOREIGN KEY (`categoria_id`) REFERENCES `governanca_categorias_membro` (`id`),
  ADD CONSTRAINT `governanca_quota_con_tipo_id_121bedb8_fk_governanc` FOREIGN KEY (`tipo_id`) REFERENCES `governanca_tipos_quota` (`id`);

--
-- Limitadores para a tabela `governanca_recibos_voto`
--
ALTER TABLE `governanca_recibos_voto`
  ADD CONSTRAINT `governanca_recibos_voto_voto_id_487e5e0c_fk_governanca_votos_id` FOREIGN KEY (`voto_id`) REFERENCES `governanca_votos` (`id`);

--
-- Limitadores para a tabela `governanca_relatorios_consulta`
--
ALTER TABLE `governanca_relatorios_consulta`
  ADD CONSTRAINT `governanca_relatorio_consulta_id_beed54fc_fk_governanc` FOREIGN KEY (`consulta_id`) REFERENCES `governanca_consultas_publicas` (`id`),
  ADD CONSTRAINT `governanca_relatorio_criado_por_id_d8db590c_fk_usuarios_` FOREIGN KEY (`criado_por_id`) REFERENCES `usuarios` (`id`);

--
-- Limitadores para a tabela `governanca_respostas_presenca`
--
ALTER TABLE `governanca_respostas_presenca`
  ADD CONSTRAINT `governanca_respostas_assembleia_id_8d0a3986_fk_governanc` FOREIGN KEY (`assembleia_id`) REFERENCES `governanca_assembleias` (`id`),
  ADD CONSTRAINT `governanca_respostas_presenca_usuario_id_00c7529b_fk_usuarios_id` FOREIGN KEY (`usuario_id`) REFERENCES `usuarios` (`id`);

--
-- Limitadores para a tabela `governanca_votacoes_consulta`
--
ALTER TABLE `governanca_votacoes_consulta`
  ADD CONSTRAINT `governanca_votacoes__consulta_id_1c751528_fk_governanc` FOREIGN KEY (`consulta_id`) REFERENCES `governanca_consultas_publicas` (`id`);

--
-- Limitadores para a tabela `governanca_votos`
--
ALTER TABLE `governanca_votos`
  ADD CONSTRAINT `governanca_votos_delegado_de_id_d5f96332_fk_usuarios_id` FOREIGN KEY (`delegado_de_id`) REFERENCES `usuarios` (`id`),
  ADD CONSTRAINT `governanca_votos_pauta_id_b699860e_fk_governanca_pautas_id` FOREIGN KEY (`pauta_id`) REFERENCES `governanca_pautas` (`id`),
  ADD CONSTRAINT `governanca_votos_usuario_id_3ec84d05_fk_usuarios_id` FOREIGN KEY (`usuario_id`) REFERENCES `usuarios` (`id`);

--
-- Limitadores para a tabela `governanca_votos_consulta`
--
ALTER TABLE `governanca_votos_consulta`
  ADD CONSTRAINT `governanca_votos_con_votacao_id_84913e68_fk_governanc` FOREIGN KEY (`votacao_id`) REFERENCES `governanca_votacoes_consulta` (`id`),
  ADD CONSTRAINT `governanca_votos_consulta_usuario_id_bb73438b_fk_usuarios_id` FOREIGN KEY (`usuario_id`) REFERENCES `usuarios` (`id`);

--
-- Limitadores para a tabela `rh_avaliacoes`
--
ALTER TABLE `rh_avaliacoes`
  ADD CONSTRAINT `rh_avaliacoes_ciclo_id_008efbb2_fk_rh_ciclos_avaliacao_id` FOREIGN KEY (`ciclo_id`) REFERENCES `rh_ciclos_avaliacao` (`id`),
  ADD CONSTRAINT `rh_avaliacoes_colaborador_id_9a8147fb_fk_rh_colaboradores_id` FOREIGN KEY (`colaborador_id`) REFERENCES `rh_colaboradores` (`id`);

--
-- Limitadores para a tabela `rh_candidaturas`
--
ALTER TABLE `rh_candidaturas`
  ADD CONSTRAINT `rh_candidaturas_vaga_id_28775e1f_fk_rh_vagas_id` FOREIGN KEY (`vaga_id`) REFERENCES `rh_vagas` (`id`);

--
-- Limitadores para a tabela `rh_cargos_mesa`
--
ALTER TABLE `rh_cargos_mesa`
  ADD CONSTRAINT `rh_cargos_mesa_usuario_id_cc603ae2_fk_usuarios_id` FOREIGN KEY (`usuario_id`) REFERENCES `usuarios` (`id`);

--
-- Limitadores para a tabela `rh_ciclos_avaliacao`
--
ALTER TABLE `rh_ciclos_avaliacao`
  ADD CONSTRAINT `rh_ciclos_avaliacao_banca_id_7f2379b6_fk_rh_empresas_id` FOREIGN KEY (`banca_id`) REFERENCES `rh_empresas` (`id`);

--
-- Limitadores para a tabela `rh_colaboradores`
--
ALTER TABLE `rh_colaboradores`
  ADD CONSTRAINT `rh_colaboradores_banca_id_522a0980_fk_rh_empresas_id` FOREIGN KEY (`banca_id`) REFERENCES `rh_empresas` (`id`),
  ADD CONSTRAINT `rh_colaboradores_filial_id_272517b8_fk_rh_filiais_id` FOREIGN KEY (`filial_id`) REFERENCES `rh_filiais` (`id`);

--
-- Limitadores para a tabela `rh_colaborador_documentos`
--
ALTER TABLE `rh_colaborador_documentos`
  ADD CONSTRAINT `rh_colaborador_docum_colaborador_id_53fccf23_fk_rh_colabo` FOREIGN KEY (`colaborador_id`) REFERENCES `rh_colaboradores` (`id`);

--
-- Limitadores para a tabela `rh_entrevistas`
--
ALTER TABLE `rh_entrevistas`
  ADD CONSTRAINT `rh_entrevistas_candidatura_id_01e3930d_fk_rh_candidaturas_id` FOREIGN KEY (`candidatura_id`) REFERENCES `rh_candidaturas` (`id`);

--
-- Limitadores para a tabela `rh_faturas`
--
ALTER TABLE `rh_faturas`
  ADD CONSTRAINT `rh_faturas_banca_id_b7549d23_fk_rh_empresas_id` FOREIGN KEY (`banca_id`) REFERENCES `rh_empresas` (`id`),
  ADD CONSTRAINT `rh_faturas_colaborador_id_5ad58f11_fk_rh_colaboradores_id` FOREIGN KEY (`colaborador_id`) REFERENCES `rh_colaboradores` (`id`),
  ADD CONSTRAINT `rh_faturas_processamento_salari_c5d2ad0b_fk_rh_proces` FOREIGN KEY (`processamento_salarial_id`) REFERENCES `rh_processamentos` (`id`);

--
-- Limitadores para a tabela `rh_filiais`
--
ALTER TABLE `rh_filiais`
  ADD CONSTRAINT `rh_filiais_banca_id_70bdb123_fk_rh_empresas_id` FOREIGN KEY (`banca_id`) REFERENCES `rh_empresas` (`id`);

--
-- Limitadores para a tabela `rh_gestores_filial`
--
ALTER TABLE `rh_gestores_filial`
  ADD CONSTRAINT `rh_gestores_filial_colaborador_id_15285fc2_fk_rh_colabo` FOREIGN KEY (`colaborador_id`) REFERENCES `rh_colaboradores` (`id`),
  ADD CONSTRAINT `rh_gestores_filial_filial_id_9d44d5c7_fk_rh_filiais_id` FOREIGN KEY (`filial_id`) REFERENCES `rh_filiais` (`id`);

--
-- Limitadores para a tabela `rh_metricas_avaliacao`
--
ALTER TABLE `rh_metricas_avaliacao`
  ADD CONSTRAINT `rh_metricas_avaliaca_ciclo_id_620927a0_fk_rh_ciclos` FOREIGN KEY (`ciclo_id`) REFERENCES `rh_ciclos_avaliacao` (`id`);

--
-- Limitadores para a tabela `rh_notas_metricas`
--
ALTER TABLE `rh_notas_metricas`
  ADD CONSTRAINT `rh_notas_metricas_avaliacao_id_5ef59c5f_fk_rh_avaliacoes_id` FOREIGN KEY (`avaliacao_id`) REFERENCES `rh_avaliacoes` (`id`),
  ADD CONSTRAINT `rh_notas_metricas_metrica_id_0d6f639d_fk_rh_metric` FOREIGN KEY (`metrica_id`) REFERENCES `rh_metricas_avaliacao` (`id`);

--
-- Limitadores para a tabela `rh_pedidos_ferias`
--
ALTER TABLE `rh_pedidos_ferias`
  ADD CONSTRAINT `rh_pedidos_ferias_colaborador_id_5c59ebb5_fk_rh_colaboradores_id` FOREIGN KEY (`colaborador_id`) REFERENCES `rh_colaboradores` (`id`);

--
-- Limitadores para a tabela `rh_planos_integracao`
--
ALTER TABLE `rh_planos_integracao`
  ADD CONSTRAINT `rh_planos_integracao_candidatura_id_abeeb3e3_fk_rh_candid` FOREIGN KEY (`candidatura_id`) REFERENCES `rh_candidaturas` (`id`),
  ADD CONSTRAINT `rh_planos_integracao_colaborador_id_1d0e7824_fk_rh_colabo` FOREIGN KEY (`colaborador_id`) REFERENCES `rh_colaboradores` (`id`);

--
-- Limitadores para a tabela `rh_presencas`
--
ALTER TABLE `rh_presencas`
  ADD CONSTRAINT `rh_presencas_aprovado_por_id_9870d01e_fk_rh_colaboradores_id` FOREIGN KEY (`aprovado_por_id`) REFERENCES `rh_colaboradores` (`id`),
  ADD CONSTRAINT `rh_presencas_colaborador_id_88195135_fk_rh_colaboradores_id` FOREIGN KEY (`colaborador_id`) REFERENCES `rh_colaboradores` (`id`);

--
-- Limitadores para a tabela `rh_processamentos`
--
ALTER TABLE `rh_processamentos`
  ADD CONSTRAINT `rh_processamentos_banca_id_7a69abda_fk_rh_empresas_id` FOREIGN KEY (`banca_id`) REFERENCES `rh_empresas` (`id`);

--
-- Limitadores para a tabela `rh_recibos`
--
ALTER TABLE `rh_recibos`
  ADD CONSTRAINT `rh_recibos_colaborador_id_e93023ee_fk_rh_colaboradores_id` FOREIGN KEY (`colaborador_id`) REFERENCES `rh_colaboradores` (`id`),
  ADD CONSTRAINT `rh_recibos_processamento_id_29173b91_fk_rh_processamentos_id` FOREIGN KEY (`processamento_id`) REFERENCES `rh_processamentos` (`id`);

--
-- Limitadores para a tabela `rh_recibo_subsidios`
--
ALTER TABLE `rh_recibo_subsidios`
  ADD CONSTRAINT `rh_recibo_subsidios_recibo_id_0a4bd686_fk_rh_recibos_id` FOREIGN KEY (`recibo_id`) REFERENCES `rh_recibos` (`id`),
  ADD CONSTRAINT `rh_recibo_subsidios_subsidio_id_42bd3ca0_fk_rh_subsidios_id` FOREIGN KEY (`subsidio_id`) REFERENCES `rh_subsidios` (`id`);

--
-- Limitadores para a tabela `rh_subsidios`
--
ALTER TABLE `rh_subsidios`
  ADD CONSTRAINT `rh_subsidios_banca_id_6462b014_fk_rh_empresas_id` FOREIGN KEY (`banca_id`) REFERENCES `rh_empresas` (`id`);

--
-- Limitadores para a tabela `rh_subsidios_colaboradores_especificos`
--
ALTER TABLE `rh_subsidios_colaboradores_especificos`
  ADD CONSTRAINT `rh_subsidios_colabor_colaborador_id_9883e0b3_fk_rh_colabo` FOREIGN KEY (`colaborador_id`) REFERENCES `rh_colaboradores` (`id`),
  ADD CONSTRAINT `rh_subsidios_colabor_subsidio_id_f933fc46_fk_rh_subsid` FOREIGN KEY (`subsidio_id`) REFERENCES `rh_subsidios` (`id`);

--
-- Limitadores para a tabela `rh_tarefas_integracao`
--
ALTER TABLE `rh_tarefas_integracao`
  ADD CONSTRAINT `rh_tarefas_integraca_plano_id_5cec0637_fk_rh_planos` FOREIGN KEY (`plano_id`) REFERENCES `rh_planos_integracao` (`id`);

--
-- Limitadores para a tabela `rh_vagas`
--
ALTER TABLE `rh_vagas`
  ADD CONSTRAINT `rh_vagas_banca_id_8d08e0d3_fk_rh_empresas_id` FOREIGN KEY (`banca_id`) REFERENCES `rh_empresas` (`id`),
  ADD CONSTRAINT `rh_vagas_filial_id_88829763_fk_rh_filiais_id` FOREIGN KEY (`filial_id`) REFERENCES `rh_filiais` (`id`);

--
-- Limitadores para a tabela `usuarios`
--
ALTER TABLE `usuarios`
  ADD CONSTRAINT `usuarios_categoria_id_a38b1748_fk_governanc` FOREIGN KEY (`categoria_id`) REFERENCES `governanca_categorias_membro` (`id`);

--
-- Limitadores para a tabela `usuarios_cargos`
--
ALTER TABLE `usuarios_cargos`
  ADD CONSTRAINT `usuarios_cargos_atribuido_por_id_3580ad62_fk_usuarios_id` FOREIGN KEY (`atribuido_por_id`) REFERENCES `usuarios` (`id`),
  ADD CONSTRAINT `usuarios_cargos_cargo_id_9c79f074_fk_cargos_id` FOREIGN KEY (`cargo_id`) REFERENCES `cargos` (`id`),
  ADD CONSTRAINT `usuarios_cargos_usuario_id_d3f97be5_fk_usuarios_id` FOREIGN KEY (`usuario_id`) REFERENCES `usuarios` (`id`);
COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
