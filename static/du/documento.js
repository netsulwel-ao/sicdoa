function calcularDERIMP({ regimeCod, procedimento, codigoIsencao, aliquotaCol1, valorCIF }) {

  // If (
  //     (regime_aduaneiro EQ 'IM4' or regime_aduaneiro EQ 'IMS4' or regime_aduaneiro EQ 'IMV4') or
  //     (regime_aduaneiro EQ 'IM5' or regime_aduaneiro EQ 'IMS5' or regime_aduaneiro EQ 'IMV5') or
  //     ( (regime_aduaneiro EQ 'IM6' or regime_aduaneiro EQ 'IMS6' or regime_aduaneiro EQ 'IMV6') and ( Código_do_Procedimento EQ "6021" ) ) or
  //     (regime_aduaneiro EQ 'IM7' or regime_aduaneiro EQ 'IMS7' or regime_aduaneiro EQ 'IMV7') or
  //     (regime_aduaneiro EQ 'IM8' or regime_aduaneiro EQ 'IMS8' or regime_aduaneiro EQ 'IMV8')
  // ) Then
  const isRegime4 = ['IM4','IMS4','IMV4'].includes(regimeCod);
  const isRegime5 = ['IM5','IMS5','IMV5'].includes(regimeCod);
  const isRegime6 = ['IM6','IMS6','IMV6'].includes(regimeCod);
  const isRegime7 = ['IM7','IMS7','IMV7'].includes(regimeCod);
  const isRegime8 = ['IM8','IMS8','IMV8'].includes(regimeCod);

  const aplicaRegime = (
    isRegime4 ||
    isRegime5 ||
    (isRegime6 && procedimento === '6021') ||
    isRegime7 ||
    isRegime8
  );
  if (!aplicaRegime) return { valor: 0, acao: 'N/A', credito: '0' };

  // Num01 := RateCol(ComCod, 1)
  const Num01 = parseFloat(aliquotaCol1) || 0;

  // Num02 := ItmCIFNcy
  const Num02 = parseFloat(valorCIF) || 0;

  let resultado = { valor: 0, acao: 'N/A', credito: '0' };

  // If ( Num01 > 0 ) Then
  if (Num01 > 0) {

    // Num03 := ( Num01 * Num02 ) Div 100
    const Num03 = (Num01 * Num02) / 100;

    // If (
    //     (regime_aduaneiro EQ 'IM4' or regime_aduaneiro EQ 'IMS4' or regime_aduaneiro EQ 'IMV4') or
    //     (regime_aduaneiro EQ 'IM6' or regime_aduaneiro EQ 'IMS6' or regime_aduaneiro EQ 'IMV6') or
    //     ( (regime_aduaneiro EQ 'IM5' or regime_aduaneiro EQ 'IMS5' or regime_aduaneiro EQ 'IMV5') and ( Código_do_Procedimento EQ "5200" ) )
    // ) Then
    if (isRegime4 || isRegime6 || (isRegime5 && procedimento === '5200')) {

      // If ( Código_do_Procedimento <> "4400" ) Then
      if (procedimento !== '4400') {

        // Action := DoTax ( "02K" , "1" , Num02 , Num01 , Num03 )
        // ✅ DEVE PAGAR — Registo do imposto de importação (02K) com crédito "1"
        // Crédito "1" = importação definitiva, o declarante PAGA o imposto na íntegra.
        // Valor a pagar = Num03 = (alíquota × CIF) / 100
        // Exemplo: CIF = 1.000.000 KZ, alíquota = 5% → DERIMP = 50.000 KZ a pagar
        // Aplica-se a: IM/IMS/IMV4 (importação definitiva),
        //              IM/IMS/IMV6 (reimportação),
        //              IM/IMS/IMV5 + proc=5200 (importação temporária que se tornou definitiva)
        // EXCEÇÃO: proc=4400 bloqueia sempre o pagamento (mercadoria em trânsito/depósito)
        resultado = { valor: Num03, acao: 'DoTax', credito: '1', base: Num02, taxa: Num01 };
      }
      // Endif
      // ⛔ Se proc=4400: NÃO PAGA — mercadoria em depósito aduaneiro ou trânsito,
      //    o imposto não é liquidado neste momento.
    }
    // Endif

    // If (
    //     ( (regime_aduaneiro EQ 'IM5' or regime_aduaneiro EQ 'IMS5' or regime_aduaneiro EQ 'IMV5') and ( Código_do_Procedimento <> "5200" ) ) or
    //     (regime_aduaneiro EQ 'IM7' or regime_aduaneiro EQ 'IMS7' or regime_aduaneiro EQ 'IMV7') or
    //     (regime_aduaneiro EQ 'IM8' or regime_aduaneiro EQ 'IMS8' or regime_aduaneiro EQ 'IMV8')
    // ) Then
    if ((isRegime5 && procedimento !== '5200') || isRegime7 || isRegime8) {

      // Action := DoTax ( "02K" , "0" , Num02 , Num01 , Num03 )
      // ⏸️ REGISTO EM SUSPENSÃO — Imposto calculado mas NÃO pago imediatamente.
      // Crédito "0" = regime suspensivo, o imposto fica registado no sistema
      // mas em estado de suspensão — só será exigido se a mercadoria não sair
      // do país dentro do prazo ou se mudar para regime definitivo.
      // Valor calculado = Num03 = (alíquota × CIF) / 100 (igual ao DoTax "1")
      // Aplica-se a: IM/IMS/IMV5 + proc≠5200 (importação temporária ainda activa),
      //              IM/IMS/IMV7 (armazenagem/entreposto aduaneiro),
      //              IM/IMS/IMV8 (trânsito e transbordo)
      resultado = { valor: Num03, acao: 'DoTax', credito: '0', base: Num02, taxa: Num01 };
    }
    // Endif

  }
  // Endif
  // ℹ️ Se alíquota = 0: o código pautal tem taxa zero na pauta aduaneira,
  //    nenhum DoTax é executado mas os blocos RelTax/DelTax abaixo
  //    continuam a ser avaliados independentemente.

  // If ( (regime_aduaneiro EQ 'IM6' or regime_aduaneiro EQ 'IMS6' or regime_aduaneiro EQ 'IMV6')
  //      and Código_do_Procedimento EQ "6021"
  //      and Código da Isenção EQ "003" ) Then
  if (isRegime6 && procedimento === '6021' && codigoIsencao === '003') {

    // Action := RelTax ( "02K" , "1" , Num02 , Num01 , 0 )
    // 🟡 ISENTO COM REGISTO — NÃO PAGA, mas o imposto fica registado no sistema.
    // RelTax = relevar/isentar: o sistema regista o imposto com valor = 0
    // e guarda o motivo da isenção (código "003" = isenção por acordo internacional
    // ou reimportação com isenção justificada) para fins de auditoria e controlo.
    // Sobrescreve qualquer DoTax calculado anteriormente para este regime.
    // Aplica-se a: reimportação (IM/IMS/IMV6 + proc=6021) com isenção código 003.
    resultado = { valor: 0, acao: 'RelTax', credito: '1', base: Num02, taxa: Num01 };
  }
  // Endif

  // If ( regime_aduaneiro EQ 'IMS6' and Código_do_Procedimento EQ "6022" ) Then
  if (regimeCod === 'IMS6' && procedimento === '6022') {

    // Action := DelTax ( "02K" )
    // 🔴 ANULAÇÃO TOTAL — NÃO PAGA e o registo do imposto é completamente eliminado.
    // DelTax = deletar: ao contrário do RelTax (que guarda o registo com valor 0),
    // o DelTax apaga completamente o imposto 02K como se nunca tivesse sido calculado.
    // Usado em declarações de anulação/rectificação (IMS6 + proc=6022):
    // quando uma reimportação simplificada é anulada, o imposto anterior é removido.
    // NOTA: só se aplica a IMS6 (declaração simplificada), não a IM6 nem IMV6.
    resultado = { valor: 0, acao: 'DelTax', credito: '0' };
  }
  // Endif

  // If ( (regime_aduaneiro EQ 'IM7' or regime_aduaneiro EQ 'IMS7' or regime_aduaneiro EQ 'IMV7')
  //      and ( Código_do_Procedimento EQ "7100" ) ) Then
  if (isRegime7 && procedimento === '7100') {

    // Action := RelTax ( "02K" , "1" , Num02 , Num01 , 0 )
    // 🟡 ISENTO COM REGISTO — NÃO PAGA, mas o imposto fica registado no sistema.
    // RelTax: o imposto é relevado (isento) porque a mercadoria está a ser
    // reexportada (proc=7100 = saída definitiva de mercadoria em armazenagem).
    // O sistema guarda o registo para controlo — a mercadoria entrou em regime
    // suspensivo (DoTax crédito "0" calculado acima) mas ao sair com proc=7100
    // a suspensão é convertida em isenção definitiva: não há pagamento.
    // Sobrescreve o DoTax "0" calculado no bloco anterior para IM/IMS/IMV7.
    resultado = { valor: 0, acao: 'RelTax', credito: '1', base: Num02, taxa: Num01 };
  }
  // Endif

  // Endif
  return resultado;
}










function calcularIEC({ regimeCod, procedimento, codigoIsencao, aliquotaCol2, valorCIF }) {

  // Num01 := RateCol(ComCod, 2)
  const Num01 = parseFloat(aliquotaCol2) || 0;

  // Num02 := ItmCIFNcy
  const Num02 = parseFloat(valorCIF) || 0;

  // Num03 := ( Num01 * Num02 ) Div 100
  const Num03 = (Num01 * Num02) / 100;

  // If (
  //     (regime_aduaneiro EQ 'IM4' or regime_aduaneiro EQ 'IMS4') or
  //     ( (regime_aduaneiro EQ 'IM6' or regime_aduaneiro EQ 'IMS6') and ( Código_do_Procedimento EQ "6021" ) )
  // ) Then
  if (
    ['IM4','IMS4'].includes(regimeCod) ||
    (['IM6','IMS6'].includes(regimeCod) && procedimento === '6021')
  ) {

    // Action := DoTax ( "IEC" , "1" , Num02 , Num01 , Num03 )
    // ✅ DEVE PAGAR — Registo do Imposto Especial de Consumo (IEC) com crédito "1".
    // Crédito "1" = liquidação imediata, o declarante PAGA o IEC na íntegra
    // no momento do desalfandegamento da mercadoria.
    // A alíquota vem da coluna 2 da pauta aduaneira (direito de consumo),
    // que é específica para produtos sujeitos a IEC (tabaco, álcool, veículos, etc).
    // Valor a pagar = Num03 = (alíquota_col2 × CIF) / 100
    // Exemplo: CIF = 2.000.000 KZ, alíquota col2 = 30% → IEC = 600.000 KZ a pagar
    // Aplica-se a:
    //   IM4  = importação definitiva normal
    //   IMS4 = importação definitiva simplificada
    //   IM6 + proc=6021  = reimportação definitiva
    //   IMS6 + proc=6021 = reimportação definitiva simplificada
    return { valor: Num03, acao: 'DoTax', credito: '1', base: Num02, taxa: Num01 };
  }
  // Endif

  // If (
  //     ( regime_aduaneiro EQ 'IM8' ) and
  //     ( ( Código_do_Procedimento EQ "8000" or Código_do_Procedimento EQ "8100" ) and ( Código da Isenção EQ "000" ) )
  // ) Then
  if (
    regimeCod === 'IM8' &&
    (procedimento === '8000' || procedimento === '8100') &&
    codigoIsencao === '000'
  ) {

    // Action := DoTax ( "IEC" , "1" , Num02 , Num01 , Num03 )
    // ✅ DEVE PAGAR — Registo do IEC com crédito "1" para regime especial IM8.
    // Crédito "1" = liquidação imediata, o declarante PAGA o IEC na íntegra.
    // Condição adicional: codigoIsencao = "000" significa SEM isenção aplicada —
    // se houvesse um código de isenção diferente de "000", o IEC não seria cobrado.
    // Aplica-se a:
    //   IM8 + proc=8000 = trânsito e transbordo sem isenção
    //   IM8 + proc=8100 = trânsito e transbordo sem isenção (variante)
    // Nota: proc=8300 não está incluído nesta condição — IM8+8300 não paga IEC.
    return { valor: Num03, acao: 'DoTax', credito: '1', base: Num02, taxa: Num01 };
  }
  // Endif

  // ⛔ NÃO PAGA — Nenhuma das condições se aplicou.
  // O IEC não é cobrado quando:
  //   - O regime não é IM4, IMS4, IM6+6021, IMS6+6021, nem IM8+8000/8100
  //   - O código pautal não tem alíquota na coluna 2 (produto não sujeito a IEC)
  //   - IM8 com proc=8000 ou 8100 mas com código de isenção diferente de "000"
  return { valor: 0, acao: 'N/A', credito: '0', taxa: 0 };
}












function calcularEMGEAD({ regimeCod, procedimento, codigoPautal, paisOrigem,
                           valorCIF, valorFatura, itemNumber }) {

  const Num02_CIF = parseFloat(valorCIF)    || 0;
  const Num02_FOB = parseFloat(valorFatura) || 0;
  const cp        = String(codigoPautal || '').replace(/\./g, '');

  let resultado = { valor: 0, acao: 'N/A', credito: '0', taxa: 0 };

  // ════════════════════════════════════════════════════════════════
  // If (
  //     (regime_aduaneiro EQ 'EX1' or regime_aduaneiro EQ 'EXS1' or regime_aduaneiro EQ 'EXV1') or
  //     (regime_aduaneiro EQ 'EX2' or regime_aduaneiro EQ 'EXS2' or regime_aduaneiro EQ 'EXV2') or
  //     (regime_aduaneiro EQ 'EX3' or regime_aduaneiro EQ 'EXS3' or regime_aduaneiro EQ 'EXV3')
  // ) Then
  // ════════════════════════════════════════════════════════════════
  const isEX1 = ['EX1','EXS1','EXV1'].includes(regimeCod);
  const isEX2 = ['EX2','EXS2','EXV2'].includes(regimeCod);
  const isEX3 = ['EX3','EXS3','EXV3'].includes(regimeCod);

  if (isEX1 || isEX2 || isEX3) {

    // If (regime_aduaneiro EQ 'EX1' or regime_aduaneiro EQ 'EXS1' or regime_aduaneiro EQ 'EXV1') Then
    if (isEX1) {

      // If ( ComCod EQ "49070010" ) Then
      if (cp === '49070010') {

        // If ( ItmNber EQ 1 ) Then
        if (itemNumber === 1) {

          const Num01 = 88;
          const Num02 = 240;
          const Num03 = Num01 * Num02; // 88 × 240 = 21.120 KZ

          // Action := DoTax ( "05M" , "1" , Num02 , Num01 , Num03 )
          // ✅ DEVE PAGAR — Taxa fixa de emolumentos para documentos timbrados/selos (49070010).
          // Valor fixo = 88 (UCF) × 240 = 21.120 KZ — independente do valor da mercadoria.
          // Crédito "1" = pagamento imediato e definitivo.
          // Só se aplica ao primeiro item (ItmNber=1) — os itens seguintes não pagam.
          // Aplica-se a: EX1, EXS1, EXV1 com código pautal 49070010.
          return { valor: Num03, acao: 'DoTax', credito: '1', taxa: Num01, base: Num02 };
        }
        // Endif
        // ⛔ Item > 1: NÃO PAGA — taxa fixa só incide uma vez por declaração.
      } else {

        // Else (ComCod <> "49070010")
        // If ( cod_pais_de_Origem <> "AO" ) Then
        if (paisOrigem !== 'AO') {

          const Num01 = 0.5;
          const Num02 = Num02_FOB;
          const Num03 = (Num01 * Num02) / 100;

          // Action := DoTax ( "05M" , "1" , Num02 , Num01 , Num03 )
          // ✅ DEVE PAGAR — Emolumentos de 0,5% sobre o FOB para mercadorias
          // exportadas com origem estrangeira (país de origem ≠ Angola).
          // Crédito "1" = pagamento imediato e definitivo.
          // Valor = 0,5% × FOB
          // Exemplo: FOB = 5.000.000 KZ → EMGEAD = 25.000 KZ
          // Aplica-se a: EX1/EXS1/EXV1 com país de origem diferente de AO.
          return { valor: Num03, acao: 'DoTax', credito: '1', taxa: Num01, base: Num02 };
        }
        // Endif
        // ⛔ País de origem = AO: NÃO PAGA — mercadoria de origem angolana
        //    exportada em EX1 não está sujeita a emolumentos percentuais.
      }
      // Endif (ComCod)
    }
    // Endif (EX1)

    // If ( regime_aduaneiro EQ 'EX2' ) Then
    if (regimeCod === 'EX2') {

      // If ( ItmNber EQ 1 ) Then
      if (itemNumber === 1) {

        const Num01 = 88;
        const Num02 = 240;
        const Num03 = Num01 * Num02; // 88 × 240 = 21.120 KZ

        // Action := DoTax ( "05M" , "1" , Num02 , Num01 , Num03 )
        // ✅ DEVE PAGAR — Taxa fixa de emolumentos para exportação temporária (EX2).
        // Valor fixo = 88 (UCF) × 240 = 21.120 KZ — independente do valor da mercadoria.
        // Crédito "1" = pagamento imediato e definitivo.
        // Só se aplica ao primeiro item (ItmNber=1) — os itens seguintes não pagam.
        // NOTA: só EX2 puro — EXS2 e EXV2 têm condições próprias abaixo.
        return { valor: Num03, acao: 'DoTax', credito: '1', taxa: Num01, base: Num02 };
      }
      // Endif
      // ⛔ Item > 1: NÃO PAGA — taxa fixa só incide uma vez por declaração.
    }
    // Endif (EX2)

    // If ( regime_aduaneiro EQ 'EXS2' and Código_do_Procedimento EQ "2200" ) Then
    if (regimeCod === 'EXS2' && procedimento === '2200') {

      // If ( ItmNber EQ 1 ) Then
      if (itemNumber === 1) {

        const Num01 = 88;
        const Num02 = 240;
        const Num03 = Num01 * Num02; // 88 × 240 = 21.120 KZ

        // Action := DoTax ( "05M" , "1" , Num02 , Num01 , Num03 )
        // ✅ DEVE PAGAR — Taxa fixa de emolumentos para exportação temporária
        // simplificada (EXS2) com procedimento 2200.
        // Valor fixo = 88 (UCF) × 240 = 21.120 KZ.
        // Crédito "1" = pagamento imediato e definitivo.
        // Só aplica ao primeiro item e APENAS quando proc=2200.
        // EXS2 com outros procedimentos NÃO paga emolumentos.
        return { valor: Num03, acao: 'DoTax', credito: '1', taxa: Num01, base: Num02 };
      }
      // Endif
      // ⛔ Item > 1: NÃO PAGA.
    }
    // Endif (EXS2+2200)

    // If ( regime_aduaneiro EQ 'EX3' ) Then
    if (regimeCod === 'EX3') {

      // If ( ItmNber EQ 1 ) Then
      if (itemNumber === 1) {

        const Num01 = 88;
        const Num02 = 240;
        const Num03 = Num01 * Num02; // 88 × 240 = 21.120 KZ

        // Action := DoTax ( "05M" , "1" , Num02 , Num01 , Num03 )
        // ✅ DEVE PAGAR — Taxa fixa de emolumentos para reexportação (EX3).
        // Valor fixo = 88 (UCF) × 240 = 21.120 KZ — independente do valor da mercadoria.
        // Crédito "1" = pagamento imediato e definitivo.
        // Só se aplica ao primeiro item (ItmNber=1).
        // NOTA: só EX3 puro — EXS3 e EXV3 não estão cobertos por esta condição.
        return { valor: Num03, acao: 'DoTax', credito: '1', taxa: Num01, base: Num02 };
      }
      // Endif
      // ⛔ Item > 1: NÃO PAGA.
    }
    // Endif (EX3)
  }
  // Endif (bloco EX)

  // ════════════════════════════════════════════════════════════════
  // If (
  //     (regime_aduaneiro EQ 'IM4' or regime_aduaneiro EQ 'IMS4' or regime_aduaneiro EQ 'IMV4') or
  //     (regime_aduaneiro EQ 'IM5' or regime_aduaneiro EQ 'IMS5' or regime_aduaneiro EQ 'IMV5') or
  //     (regime_aduaneiro EQ 'IM6' or regime_aduaneiro EQ 'IMS6' or regime_aduaneiro EQ 'IMV6') or
  //     (regime_aduaneiro EQ 'IM7' or regime_aduaneiro EQ 'IMS7' or regime_aduaneiro EQ 'IMV7')
  // ) Then
  // ════════════════════════════════════════════════════════════════
  const isRegime4 = ['IM4','IMS4','IMV4'].includes(regimeCod);
  const isRegime5 = ['IM5','IMS5','IMV5'].includes(regimeCod);
  const isRegime6 = ['IM6','IMS6','IMV6'].includes(regimeCod);
  const isRegime7 = ['IM7','IMS7','IMV7'].includes(regimeCod);

  if (isRegime4 || isRegime5 || isRegime6 || isRegime7) {

    // If ( (IM4 or IMS4 or IMV4) and Código_do_Procedimento <> "4400" ) Then
    if (isRegime4 && procedimento !== '4400') {

      const Num01_base = 2;
      const Num02_base = Num02_CIF;
      let   Num03_base = (Num01_base * Num02_base) / 100;

      // Action := DoTax ( "05M" , "1" , Num02 , Num01 , Num03 )
      // ✅ DEVE PAGAR — Emolumentos de 2% sobre o CIF para importação definitiva (IM4/IMS4/IMV4).
      // Crédito "1" = pagamento imediato e definitivo.
      // Valor = 2% × CIF
      // Exemplo: CIF = 3.000.000 KZ → EMGEAD = 60.000 KZ
      // EXCEÇÃO: proc=4400 bloqueia o pagamento (mercadoria em depósito/trânsito).
      resultado = { valor: Num03_base, acao: 'DoTax', credito: '1', taxa: Num01_base, base: Num02_base };

      // If ( ComCod EQ "49070010" or ComCod EQ "49070090" ) Then
      if (cp === '49070010' || cp === '49070090') {

        const Num01_esp = 88;
        const Num02_esp = 800;
        const Num03_esp = Num01_esp * Num02_esp; // 88 × 800 = 70.400 KZ

        // Action := UpdTax ( "05M" , "1" , Num02 , Num01 , Num03 )
        // ✅ DEVE PAGAR (VALOR ACTUALIZADO) — Para documentos timbrados/selos (49070010/49070090)
        // o DoTax de 2% calculado acima é SUBSTITUÍDO por uma taxa fixa maior.
        // UpdTax = actualizar: sobrescreve o valor anterior de 2% pelo valor fixo.
        // Novo valor = 88 (UCF) × 800 = 70.400 KZ — independente do CIF.
        // Aplica-se a: IM4/IMS4/IMV4 com código pautal 49070010 ou 49070090.
        resultado = { valor: Num03_esp, acao: 'UpdTax', credito: '1', taxa: Num01_esp, base: Num02_esp };
      }
      // Endif (ComCod especial)

      return resultado;
    }
    // Endif (IM4 + proc≠4400)
    // ⛔ IM4/IMS4/IMV4 + proc=4400: NÃO PAGA — mercadoria em depósito aduaneiro.

    // If ( regime_aduaneiro EQ 'IM5' ) Then
    if (regimeCod === 'IM5') {

      const Num01 = 2;
      const Num02 = Num02_CIF;
      const Num03 = (Num01 * Num02) / 100;

      // Action := DoTax ( "05M" , "1" , Num02 , Num01 , Num03 )
      // ✅ DEVE PAGAR — Emolumentos de 2% sobre o CIF para importação temporária (IM5).
      // Crédito "1" = pagamento imediato e definitivo.
      // NOTA: apenas IM5 puro — IMS5 e IMV5 não estão cobertos por esta condição.
      // Valor = 2% × CIF
      return { valor: Num03, acao: 'DoTax', credito: '1', taxa: Num01, base: Num02 };
    }
    // Endif (IM5)

    // If ( regime_aduaneiro EQ 'IM6' ) Then
    if (regimeCod === 'IM6') {

      // If ( Código_do_Procedimento EQ "6021" ) Then
      if (procedimento === '6021') {

        const Num01 = Num02_CIF; // CIF como Num01 (ordem trocada no original)
        const Num02 = 2;
        const Num03 = (Num01 * Num02) / 100;

        // Action := DoTax ( "05M" , "1" , Num02 , Num01 , Num03 )
        // ✅ DEVE PAGAR — Emolumentos de 2% sobre o CIF para reimportação definitiva (IM6+6021).
        // Crédito "1" = pagamento imediato e definitivo.
        // NOTA: na regra original Num01=CIF e Num02=2 (ordem trocada na atribuição),
        // mas o cálculo Num03 = (CIF × 2) / 100 está correcto.
        // Valor = 2% × CIF
        return { valor: Num03, acao: 'DoTax', credito: '1', taxa: Num02, base: Num01 };

      } else {

        // Else (proc ≠ 6021)
        // If ( ItmNber EQ 1 ) Then
        if (itemNumber === 1) {

          const Num01 = 88;
          const Num02 = 240;
          const Num03 = Num01 * Num02; // 88 × 240 = 21.120 KZ

          // Action := DoTax ( "05M" , "1" , Num02 , Num01 , Num03 )
          // ✅ DEVE PAGAR — Taxa fixa de emolumentos para IM6 com outros procedimentos.
          // Valor fixo = 88 (UCF) × 240 = 21.120 KZ — independente do CIF.
          // Crédito "1" = pagamento imediato e definitivo.
          // Só se aplica ao primeiro item (ItmNber=1).
          return { valor: Num03, acao: 'DoTax', credito: '1', taxa: Num01, base: Num02 };
        }
        // Endif
        // ⛔ Item > 1: NÃO PAGA — taxa fixa só incide uma vez por declaração.
      }
      // Endif (proc=6021)

    } else {

      // Else (regime ≠ IM6) — avalia IMS6
      // If ( regime_aduaneiro EQ 'IMS6' and Código_do_Procedimento EQ "6022" ) Then
      if (regimeCod === 'IMS6' && procedimento === '6022') {

        // If ( ItmNber EQ 1 ) Then
        if (itemNumber === 1) {

          const Num01 = 88;
          const Num02 = 240;
          const Num03 = Num01 * Num02; // 88 × 240 = 21.120 KZ

          // Action := DoTax ( "05M" , "1" , Num02 , Num01 , Num03 )
          // ✅ DEVE PAGAR — Taxa fixa de emolumentos para declaração de anulação
          // de reimportação simplificada (IMS6 + proc=6022).
          // Valor fixo = 88 (UCF) × 240 = 21.120 KZ.
          // Crédito "1" = pagamento imediato e definitivo.
          // Só se aplica ao primeiro item (ItmNber=1).
          return { valor: Num03, acao: 'DoTax', credito: '1', taxa: Num01, base: Num02 };
        }
        // Endif
        // ⛔ Item > 1: NÃO PAGA.
      }
      // Endif (IMS6+6022)
    }
    // Endif (IM6 / else)

    // If ( IM7 or IMS7 or IMV7 ) Then
    if (isRegime7) {

      // If ( ItmNber EQ 1 ) Then
      if (itemNumber === 1) {

        const Num01 = 88;
        const Num02 = 240;
        const Num03 = Num01 * Num02; // 88 × 240 = 21.120 KZ

        // If ( Código_do_Procedimento <> "7100" ) Then
        if (procedimento !== '7100') {

          // Action := DoTax ( "05M" , "1" , Num02 , Num01 , Num03 )
          // ✅ DEVE PAGAR — Taxa fixa de emolumentos para armazenagem/entreposto (IM7/IMS7/IMV7).
          // Valor fixo = 88 (UCF) × 240 = 21.120 KZ — independente do CIF.
          // Crédito "1" = pagamento imediato e definitivo.
          // Só se aplica ao primeiro item (ItmNber=1).
          return { valor: Num03, acao: 'DoTax', credito: '1', taxa: Num01, base: Num02 };

        } else {

          // Action := DoTax ( "05M" , "0" , Num02 , Num01 , Num03 )
          // ⏸️ REGISTO EM SUSPENSÃO — O valor é calculado mas NÃO pago imediatamente.
          // Crédito "0" = suspensão: proc=7100 significa reexportação da mercadoria
          // que estava em armazenagem — os emolumentos ficam suspensos porque
          // a mercadoria vai sair do país sem ser desalfandegada definitivamente.
          // Valor calculado = 88 × 240 = 21.120 KZ (igual ao crédito "1" mas em suspensão).
          return { valor: Num03, acao: 'DoTax', credito: '0', taxa: Num01, base: Num02 };
        }
        // Endif (proc=7100)
      }
      // Endif (ItmNber=1)
      // ⛔ Item > 1: NÃO PAGA — taxa fixa só incide uma vez por declaração.
    }
    // Endif (IM7)
  }
  // Endif (bloco IM4-IM7)

  // ════════════════════════════════════════════════════════════════
  // If ( regime_aduaneiro EQ 'IM8' or regime_aduaneiro EQ 'IMS8' or regime_aduaneiro EQ 'IMV8' ) Then
  // ════════════════════════════════════════════════════════════════
  const isRegime8 = ['IM8','IMS8','IMV8'].includes(regimeCod);

  if (isRegime8) {

    // If ( ItmNber EQ 1 ) Then
    if (itemNumber === 1) {

      const Num01 = 1;

      // If ( Código_do_Procedimento EQ "8100" or Código_do_Procedimento EQ "8300" ) Then
      if (procedimento === '8100' || procedimento === '8300') {

        const Num02 = 56200;
        const Num03 = Num01 * Num02; // 1 × 56.200 = 56.200 KZ

        // Action := DoTax ( "05M" , "1" , Num02 , Num01 , Num03 )
        // ✅ DEVE PAGAR — Taxa fixa de 56.200 KZ para trânsito e transbordo (IM8/IMS8/IMV8).
        // Crédito "1" = pagamento imediato e definitivo.
        // Valor fixo = 1 × 56.200 = 56.200 KZ — completamente independente do CIF ou FOB.
        // Só se aplica ao primeiro item (ItmNber=1).
        // Aplica-se a: proc=8100 (trânsito) e proc=8300 (transbordo).
        // NOTA: proc=8000 e outros procedimentos IM8 NÃO pagam EMGEAD.
        return { valor: Num03, acao: 'DoTax', credito: '1', taxa: Num01, base: Num02 };
      }
      // Endif (proc=8100 ou 8300)
      // ⛔ IM8 com proc≠8100 e proc≠8300: NÃO PAGA EMGEAD.
    }
    // Endif (ItmNber=1)
    // ⛔ Item > 1: NÃO PAGA — taxa fixa só incide uma vez por declaração.
  }
  // Endif (IM8)

  // ⛔ NÃO PAGA — Nenhuma condição se aplicou.
  return { valor: 0, acao: 'N/A', credito: '0', taxa: 0 };
}



function calcularDEREXP({ regimeCod, procedimento, codigoPautal, paisOrigem,
                           valorFatura, exportador, inListTar }) {

  const Num01_INV = parseFloat(valorFatura) || 0;

  let resultado = { valor: 0, acao: 'N/A', credito: '0', taxa: 0, base: 0 };

  // ════════════════════════════════════════════════════════════════
  // If (
  //     regime_aduaneiro EQ 'EX1' or regime_aduaneiro EQ 'EXS1' or regime_aduaneiro EQ 'EXV1'
  // ) Then
  // ════════════════════════════════════════════════════════════════
  const isEX1 = ['EX1', 'EXS1', 'EXV1'].includes(regimeCod);

  if (isEX1) {

    // Num01 := ItmInvNcy
    const Num01 = Num01_INV;

    // ── Bloco CPEXDE ─────────────────────────────────────────────
    // If ( InListTar ( "CPEXDE" ) EQ 0 ) Then
    if (inListTar("CPEXDE") === 0) {

      let Num02;

      // If ( ComCod EQ "96011000" ) or ( ComCod EQ "96019000" ) or ( ComCod EQ "05071000" ) Then
      if (codigoPautal === "96011000" || codigoPautal === "96019000" || codigoPautal === "05071000") {
        Num02 = 50;
      } else {
        Num02 = 2;
      }

      const Num03 = (Num01 * Num02) / 100;

      // Action := DoTax ( "01K" , "1" , Num01 , Num02 , Num03 )
      // ✅ DEVE PAGAR — Direitos de exportação sobre o valor de factura (ItmInvNcy).
      // Taxa = 50% para marfim/ossos (96011000, 96019000, 05071000),
      // ou 2% para todas as outras mercadorias da lista CPEXDE.
      // Crédito "1" = pagamento imediato e definitivo.
      // Valor = taxa% × Factura
      // Exemplo: Factura = 5.000.000 KZ, taxa=2% → DEREXP = 100.000 KZ
      resultado = { valor: Num03, acao: 'DoTax', credito: '1', taxa: Num02, base: Num01 };

    } else {

      // Else ( InListTar("CPEXDE") <> 0 )
      // If ( cod_pais_de_Origem <> "AO" ) Then
      if (paisOrigem !== "AO") {

        const Num02 = 20;
        const Num03 = (Num01 * Num02) / 100;

        // Action := DoTax ( "01K" , "1" , Num01 , Num02 , Num03 )
        // ✅ DEVE PAGAR — Taxa de 20% para mercadorias NÃO pertencentes à lista
        // CPEXDE mas com origem estrangeira (país de origem ≠ AO).
        // Crédito "1" = pagamento imediato e definitivo.
        // Valor = 20% × Factura
        // Exemplo: Factura = 5.000.000 KZ → DEREXP = 1.000.000 KZ
        resultado = { valor: Num03, acao: 'DoTax', credito: '1', taxa: Num02, base: Num01 };
      }
      // ⛔ Origem AO + fora da lista CPEXDE: NÃO PAGA direitos de exportação.
    }
    // Endif (CPEXDE)

    // ── Exclusão para documentos timbrados ───────────────────────
    // If ( ComCod EQ "49070010" ) Then
    if (codigoPautal === "49070010") {

      // Action := DelTax ( "01K" )
      // 🔴 ANULAÇÃO TOTAL — O imposto 01K é completamente eliminado
      // para documentos timbrados/selos (49070010).
      // DelTax apaga o registo como se nunca tivesse sido calculado.
      // Sobrescreve qualquer DoTax calculado anteriormente.
      resultado = { valor: 0, acao: 'DelTax', credito: '0', taxa: 0, base: 0 };
    }
    // Endif (49070010)

    // ── Bloco PRODUTOEXPORTACAO ───────────────────────────────────
    // If ( ( InListTar ( "PRODUTOEXPORTACAO" ) EQ 0 ) and ( cod_pais_de_Origem <> "AO" ) ) Then
    if (inListTar("PRODUTOEXPORTACAO") === 0 && paisOrigem !== "AO") {

      const Num04 = 70;
      const Num05 = (Num01 * Num04) / 100;

      // Action := UpdTax ( "01K" , "1" , Num01 , Num04 , Num05 )
      // ✅ VALOR ACTUALIZADO — Taxa de 70% para mercadorias da lista
      // PRODUTOEXPORTACAO com origem estrangeira (país de origem ≠ AO).
      // UpdTax sobrescreve o DoTax calculado anteriormente (2%, 20% ou 50%).
      // Crédito "1" = pagamento imediato e definitivo.
      // Valor = 70% × Factura
      // Exemplo: Factura = 5.000.000 KZ → DEREXP = 3.500.000 KZ
      resultado = { valor: Num05, acao: 'UpdTax', credito: '1', taxa: Num04, base: Num01 };
    }
    // ⛔ Origem AO ou fora da lista PRODUTOEXPORTACAO: não actualiza o imposto.
    // Endif (PRODUTOEXPORTACAO)

    // ── Bloco combustíveis (Exporter específico) ─────────────────
    // If ( Exporter <> "5410003284" ) Then
    if (exportador !== "5410003284") {

      // If ( ComCod EQ "27101212" ) or ( ComCod EQ "27101213" ) or ( ComCod EQ "27101214" ) Then
      if (codigoPautal === "27101212" || codigoPautal === "27101213" || codigoPautal === "27101214") {

        const Num06 = 230;
        const Num07 = (Num01 * Num06) / 100;

        // If ( cod_pais_de_Origem EQ "AO" ) Then
        if (paisOrigem === "AO") {

          // Action := DoTax ( "01K" , "1" , Num01 , Num06 , Num07 )
          // ✅ DEVE PAGAR — Taxa de 230% sobre o valor de factura para
          // combustíveis (27101212, 27101213, 27101214) de origem angolana.
          // DoTax porque ainda não havia imposto registado para origem AO.
          // Crédito "1" = pagamento imediato e definitivo.
          // Valor = 230% × Factura
          // Exemplo: Factura = 1.000.000 KZ → DEREXP = 2.300.000 KZ
          resultado = { valor: Num07, acao: 'DoTax', credito: '1', taxa: Num06, base: Num01 };

        } else {

          // Action := UpdTax ( "01K" , "1" , Num01 , Num06 , Num07 )
          // ✅ VALOR ACTUALIZADO — Taxa de 230% para combustíveis de origem
          // estrangeira. UpdTax porque já existia um DoTax anterior (20% ou 70%)
          // que é agora sobrescrito pela taxa específica de combustíveis.
          // Crédito "1" = pagamento imediato e definitivo.
          // Valor = 230% × Factura
          // Exemplo: Factura = 1.000.000 KZ → DEREXP = 2.300.000 KZ
          resultado = { valor: Num07, acao: 'UpdTax', credito: '1', taxa: Num06, base: Num01 };
        }
        // Endif (paisOrigem)
      }
      // Endif (combustíveis)
    }
    // ⛔ Exporter = "5410003284": isento da taxa especial de combustíveis.
    // Endif (Exporter)

    // ── Bloco CPEXDMB ─────────────────────────────────────────────
    // If ( InListTar ( "CPEXDMB" ) EQ 0 ) Then
    if (inListTar("CPEXDMB") === 0) {

      const Num08 = 5;
      const Num09 = (Num01 * Num08) / 100;

      // Action := DoTax ( "01K" , "1" , Num01 , Num08 , Num09 )
      // ✅ DEVE PAGAR — Taxa de 5% para mercadorias da lista CPEXDMB
      // (produtos sujeitos a taxa reduzida de exportação).
      // Crédito "1" = pagamento imediato e definitivo.
      // NOTA: este DoTax aplica-se independentemente dos blocos anteriores,
      // podendo sobrescrever os valores já calculados acima.
      // Valor = 5% × Factura
      // Exemplo: Factura = 5.000.000 KZ → DEREXP = 250.000 KZ
      resultado = { valor: Num09, acao: 'DoTax', credito: '1', taxa: Num08, base: Num01 };
    }
    // ⛔ Fora da lista CPEXDMB: não aplica taxa de 5%.
    // Endif (CPEXDMB)

    return resultado;
  }
  // Endif (EX1/EXS1/EXV1)

  // ⛔ NÃO PAGA — Nenhuma condição se aplicou.
  return { valor: 0, acao: 'N/A', credito: '0', taxa: 0, base: 0 };
}


















function calcularIVA({ codigoIsencao, aliquotaCol3, valorFOB,
                        valorDERIMP, valorIEC, valorEMGEAD, valorDEREXP }) {

  // Num01 := ItmFobNcy + TaxAmt("02K") + TaxAmt("IEC") + TaxAmt("05M") + TaxAmt("01K")
  // Base de cálculo: FOB + Direitos de Importação + IEC + Emolumentos Gerais + Direitos de Exportação
  // NOTA: TaxAmt("03M") desconsiderado conforme instrução
  const Num01 = (parseFloat(valorFOB)    || 0) +
                (parseFloat(valorDERIMP) || 0) +
                (parseFloat(valorIEC)    || 0) +
                (parseFloat(valorEMGEAD) || 0) +
                (parseFloat(valorDEREXP) || 0);

  // Num02 := RateCol(ComCod, 3)
  // Taxa de IVA específica do código pautal (coluna 3 da pauta)
  const Num02 = parseFloat(aliquotaCol3) || 0;

  // Num03 := ( Num01 * Num02 ) Div 100
  const Num03 = (Num01 * Num02) / 100;

  // Action := DoTax ( "02I" , "1" , Num01 , Num02 , Num03 )
  // ✅ DEVE PAGAR — Registo do IVA (02I) com crédito "1".
  // Ponto de partida: o IVA é sempre calculado primeiro sobre a base acumulada.
  // Crédito "1" = liquidação imediata e definitiva.
  // Base = FOB + DERIMP(02K) + IEC + EMGEAD(05M) — o IVA incide sobre
  // o valor da mercadoria MAIS todos os impostos já calculados anteriormente.
  // Exemplo: FOB=1.000.000 + DERIMP=50.000 + IEC=0 + EMGEAD=20.000 = 1.070.000 KZ
  //          Taxa IVA = 14% → IVA = 149.800 KZ a pagar
  // Este valor pode ser sobrescrito pelos blocos RelTax ou DelTax abaixo.
  let resultado = { valor: Num03, acao: 'DoTax', credito: '1', base: Num01, taxa: Num02 };

  // ── Verificação de Isenções (RelTax) ─────────────────────────────────
  // If (
  //     ( Código da Isenção EQ "001" ) or ( Código da Isenção EQ "002" ) or ...
  // ) Then
  const ISENCOES_RELTAX = new Set([
    '001','002','003','004','006','007','009','011','016','017','018','019',
    '020','021','024','025','026','028','029','033','034','035','036','037',
    '038','040','044','045','046','050','051','055','057','058','061','063',
    '064','067','068','070','071','400','401','423','435','453','461',
  ]);

  if (ISENCOES_RELTAX.has(codigoIsencao)) {

    // Action := RelTax ( "02I" , Código da Isenção , Num01 , Num02 , 0 )
    // 🟡 ISENTO COM REGISTO — NÃO PAGA, mas o registo fica no sistema.
    // RelTax = relevar/isentar: sobrescreve o DoTax calculado acima,
    // o valor do IVA passa a 0 mas a taxa e a base ficam registadas para auditoria.
    // O segundo argumento é o próprio código de isenção (não "1" nem "0") —
    // identifica exactamente qual o motivo legal da isenção aplicada.
    // Exemplos de isenções cobertas:
    //   001 = Isenção diplomática
    //   003 = Isenção por acordo internacional
    //   018 = Isenção medicamentos
    //   021 = Isenção bens alimentares básicos
    //   044 = Isenção zona franca
    //   400/401/423/435/453/461 = Regimes especiais
    // Aplica-se a qualquer regime desde que o código de isenção esteja nesta lista.
    resultado = { valor: 0, acao: 'RelTax', credito: codigoIsencao, base: Num01, taxa: Num02 };
  }
  // Endif

  // ── Verificação de Exclusão/Eliminação do Imposto (DelTax) ───────────
  // If (
  //     ( Código da Isenção EQ "012" ) or ( Código da Isenção EQ "031" ) or
  //     ( Código da Isenção EQ "405" ) or ( Código da Isenção EQ "470" ) or
  //     ( Código da Isenção EQ "471" ) or ( Código da Isenção EQ "472" ) or
  //     ( Código da Isenção EQ "473" ) or ( Código da Isenção EQ "474" )
  // ) Then
  const ISENCOES_DELTAX = new Set([
    '012','031','405','470','471','472','473','474'
  ]);

  if (ISENCOES_DELTAX.has(codigoIsencao)) {

    // Action := DelTax ( "02I" )
    // 🔴 ANULAÇÃO TOTAL — NÃO PAGA e o registo do IVA é completamente eliminado.
    // DelTax = deletar: ao contrário do RelTax (que guarda o registo com valor 0
    // e o motivo da isenção), o DelTax apaga completamente o IVA (02I)
    // como se nunca tivesse sido calculado — não fica rasto no sistema.
    // Sobrescreve qualquer DoTax ou RelTax calculado anteriormente.
    // Exemplos de isenções que eliminam o IVA:
    //   012 = Remissão fiscal
    //   031 = Remissão total
    //   405/470/471/472/473/474 = Remissões especiais de eliminação
    // A diferença prática para o declarante:
    //   RelTax → IVA=0 mas aparece na declaração com motivo de isenção
    //   DelTax → IVA desaparece completamente da declaração
    resultado = { valor: 0, acao: 'DelTax', credito: '0', base: 0, taxa: 0 };
  }
  // Endif

  return resultado;
}