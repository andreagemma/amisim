class ini:
    gamma1 = 0
    gamma2 = 1
    gamma3 = 1
    # Parametri della ricerca del passo con metodo della sezione aurea
    itesa = 100
    lambdam = 0  # Estremo inferiore della ricerca monodimensionale
    lambdaM = 0.05  # Estremo superiore
    epsilon = 0.000001  # Soglia di arresto dell'ottimizzazione monodimensionale
    epsilon2 = 10
    sa = 0.362  # segmento minore della sezione aurea
    sb = 1 - sa  # segmento maggiore della sezione aurea
    # Pesi interni ODseed - si potrebbero inserire come input esternamente alla classe StimaOD?
