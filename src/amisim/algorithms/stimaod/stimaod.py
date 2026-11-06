# -*- coding: utf-8 -*-
"""
Created on Fri Jun 11 16:16:31 2021

@author: andge
"""

import numpy as np
import pandas as pd
from .ini import ini
import pdb


class StimaOD:
    # Pesi F.O.
    gamma1 = ini.gamma1
    gamma2 = ini.gamma2
    gamma3 = ini.gamma3
    # Parametri della ricerca del passo con metodo della sezione aurea
    itesa = ini.itesa
    lambdam = ini.lambdam  # Estremo inferiore della ricerca monodimensionale
    lambdaM = ini.lambdaM  # Estremo superiore
    epsilon = ini.epsilon  # Soglia di arresto dell'ottimizzazione monodimensionale
    epsilon2 = ini.epsilon2
    sa = ini.sa  # segmento minore della sezione aurea
    sb = ini.sb  # segmento maggiore della sezione aurea
    # Pesi interni ODseed - si potrebbero inserire come input esternamente alla classe StimaOD?

    def __init__(self, loader=None, OD=None):
        # inizializzazione #load
        # load file e memorizzi in dict counts
        self.loader = loader
        self.counts = self.loader.df_counts
        self.ODseed = OD.copy()
        self.gce = []
        for i in range(0, len(self.ODseed) * 15, 15):
            self.gce.append(self.ODseed[i].mat)
        self.ite = 0
        self.fob = 1e308
        self.flows = None

    def update(self, OD, M, tstart, tend):
        """
        if self.ite == self.loader.ini.STIMA_OD_MAX_ITE:
            self.ite = 0
        self.ite += 1
        self.OD = OD
        self.M = M
        self.tstart = tstart
        self.tend = tend
        self.tstart1 = max(0, self.tstart - int(self.loader.ini.STIMA_OD_PRE))
        self.tend1 = min(1440, int(self.tend + self.loader.ini.STIMA_OD_PRE))
        self.pre_int = int(self.loader.ini.STIMA_OD_PRE / 15)
        self.t_intervals = list(range(self.tstart1, self.tend1, 15))
        self.t_corr = list(range(tstart, int(tend), 15))
        self.t_post = list(range(tstart, self.tend1, 15))
        self.zone = list(self.ODseed[0].rows)

        gi = []
        gce = []
        for item in self.t_intervals:
            gi.append(np.ravel(self.OD[item].mat))
            gce.append(np.ravel(self.gce[int(item / 15)]))

        # pdb.set_trace()
        pic = np.ones([len(self.loader.links_detected), 1])
        qce = np.ones([len(gi[0]), 1])
        #### CALCOLO FLUSSI
        flows = []
        r2_i = []
        r2_f = []

        for interval in self.t_post:
            flows_dep = np.zeros((1, M.mats[0, 0].mat.shape[0]))
            for dep in range(
                max(0, self.t_intervals.index(interval) - self.pre_int), self.t_intervals.index(interval) + 1
            ):
                flows_dep += M.mats[self.t_intervals.index(interval), dep].mat * gi[dep]
            if self.ite == 1:
                check_flows_i = pd.DataFrame()
                check_flows_i["id"] = self.loader.df_counts[self.loader.df_counts["ts"] == interval]["id"]
                check_flows_i["counts"] = self.loader.df_counts[self.loader.df_counts["ts"] == interval]["counts"]
                check_flows_i["flows"] = flows_dep.transpose()
                check_flows_i.to_excel("check_flows_i_" + str(interval) + ".xlsx")
                # import sklearn.metrics
                # r2_int_i=sklearn.metrics.r2_score(check_flows_i['counts'], check_flows_i['flows'])
                # r2_i.append(r2_int_i)
            if self.ite == int(self.loader.ini.STIMA_OD_MAX_ITE):
                check_flows_f = pd.DataFrame()
                check_flows_f["id"] = self.loader.df_counts[self.loader.df_counts["ts"] == interval]["id"]
                check_flows_f["counts"] = self.loader.df_counts[self.loader.df_counts["ts"] == interval]["counts"]
                check_flows_f["flows"] = flows_dep.transpose()
                check_flows_f.to_excel("check_flows_f_" + str(interval) + ".xlsx")
                # import sklearn.metrics
                # r2_int_f=sklearn.metrics.r2_score(check_flows_f['counts'], check_flows_f['flows'])
                # r2_f.append(r2_int_f)

            # pd.DataFrame(flows_dep).to_csv('flows_'+str(interval)+'_'+str(self.ite)+'.csv')
            flows.append(flows_dep)

        # if self.ite==1:
        #         df_r2=pd.DataFrame()
        #         df_r2['interval']=self.t_post
        #         df_r2['r2']=r2_i
        #         df_r2.to_excel('r2_i.xlsx')
        # if self.ite==int(self.loader.ini.STIMA_OD_MAX_ITE):
        #         df_r2=pd.DataFrame()
        #         df_r2['interval']=self.t_post
        #         df_r2['r2']=r2_i
        #         df_r2.to_excel('r2_f.xlsx')

        #### CALCOLO FUNZIONE OBIETTIVO
        fob1 = 0
        fob2 = 0

        #### Calcolo FOB1 - Componente seed

        for interval in self.t_corr:
            fob1 += (
                ini.gamma1
                * (
                    qce.transpose()
                    * ((gi[self.t_intervals.index(interval)] - gce[self.t_intervals.index(interval)]) ** 2)
                ).sum()
            )

        #### Calcolo FOB2 - Componente conteggi
        # TO DO: da modificare file conteggi!!!!!!!!!!!!!

        for interval in self.t_post:
            fob2 += (
                ini.gamma2
                * (
                    pic.transpose()
                    * (
                        (
                            flows[self.t_post.index(interval)]
                            - self.counts[self.counts["ts"] == interval]["counts"].values
                        )
                        ** 2
                    )
                ).sum()
            )

        self.fob = fob1 + fob2

        ### CALCOLO DEL GRADIENTE
        self.grad = []
        grad1 = []
        grad2 = []

        for interval in self.t_corr:
            grad1 = ini.gamma1 * (
                qce.transpose() * (gi[self.t_intervals.index(interval)] - gce[self.t_intervals.index(interval)])
            )
            grad2_dep = np.zeros((1, len(gi[0])))
            for dep in range(
                max(0, self.t_intervals.index(interval) - self.pre_int), self.t_intervals.index(interval) + 1
            ):
                grad2_dep += (
                    M.mats[self.t_intervals.index(interval), dep].mat.transpose()
                    * (
                        pic.transpose()
                        * (
                            flows[self.t_post.index(interval)]
                            - self.counts[self.counts["ts"] == interval]["counts"].values
                        )
                    ).transpose()
                ).transpose()
            grad2 = grad2_dep
            self.grad.append(grad1 + grad2)

        ### OTTIMIZZAZIONE: METODO SEZIONE AUREA

        ak = self.lambdam  # inizializzazione estremo inferiore
        bk = self.lambdaM  # inizializzazione estremo superiore

        gai = gi.copy()
        gbi = gi.copy()
        for interval in self.t_corr:
            gai[self.t_intervals.index(interval)] = gi[self.t_intervals.index(interval)] * (
                1 - (ak * (self.grad[self.t_intervals.index(interval) - self.pre_int][0]))
            )
            gbi[self.t_intervals.index(interval)] = gi[self.t_intervals.index(interval)] * (
                1 - (bk * (self.grad[self.t_intervals.index(interval) - self.pre_int][0]))
            )

        aak = ak + self.sa * (bk - ak)  # inizializzazione del valore intermedio minore
        bbk = ak + self.sb * (bk - ak)

        # Ricerca del passo ottimo

        for j in range(0, self.itesa):
            for interval in self.t_corr:
                gai[self.t_intervals.index(interval)] = gi[self.t_intervals.index(interval)] * (
                    1 - (aak * (self.grad[self.t_intervals.index(interval) - self.pre_int][0]))
                )
                gbi[self.t_intervals.index(interval)] = gi[self.t_intervals.index(interval)] * (
                    1 - (bbk * (self.grad[self.t_intervals.index(interval) - self.pre_int][0]))
                )

            ###CALCOLO FLUSSI PER GA e GI

            fla = []
            flb = []
            for interval in self.t_post:
                fla_dep = np.zeros((1, M.mats[0, 0].mat.shape[0]))
                flb_dep = np.zeros((1, M.mats[0, 0].mat.shape[0]))
                for dep in range(
                    max(0, self.t_intervals.index(interval) - self.pre_int), self.t_intervals.index(interval) + 1
                ):
                    fla_dep += M.mats[self.t_intervals.index(interval), dep].mat * gai[dep]
                    flb_dep += M.mats[self.t_intervals.index(interval), dep].mat * gbi[dep]
                fla.append(fla_dep)
                flb.append(flb_dep)

            #### CALCOLO FUNZIONE OBIETTIVO
            fa1 = 0
            fa2 = 0
            fb1 = 0
            fb2 = 0

            #### Calcolo FA1 e FB1 - Componente seed

            for interval in self.t_corr:
                fa1 += (
                    ini.gamma1
                    * (
                        qce.transpose()
                        * ((gai[self.t_intervals.index(interval)] - gce[self.t_intervals.index(interval)]) ** 2)
                    ).sum()
                )
                fb1 += (
                    ini.gamma1
                    * (
                        qce.transpose()
                        * ((gbi[self.t_intervals.index(interval)] - gce[self.t_intervals.index(interval)]) ** 2)
                    ).sum()
                )
            #### Calcolo FOB2 - Componente conteggi
            # TO DO: da modificare file conteggi!!!!!!!!!!!!!

            for interval in self.t_post:
                fa2 += (
                    ini.gamma2
                    * (
                        pic.transpose()
                        * (
                            (
                                fla[self.t_post.index(interval)]
                                - self.counts[self.counts["ts"] == interval]["counts"].values
                            )
                            ** 2
                        )
                    ).sum()
                )
                fb2 += (
                    ini.gamma2
                    * (
                        pic.transpose()
                        * (
                            (
                                flb[self.t_post.index(interval)]
                                - self.counts[self.counts["ts"] == interval]["counts"].values
                            )
                            ** 2
                        )
                    ).sum()
                )
            fa = fa1 + fa2
            fb = fb1 + fb2

            if fa > fb:
                ak = aak  # Nuovo estremo inferiore, posto uguale al valore intermedio minore
                aak = bbk  # Nuovo valore intermedio minore, posto uguale al valore intermedio maggiore
                bbk = ak + self.sb * (bk - ak)
            else:
                bk = bbk  # Nuovo estremo superiore, posto uguale al valore intermedio superiore
                bbk = aak  # Nuovo valore intermedio maggiore, posto uguale al valore intermedio minore
                aak = ak + self.sa * (
                    bk - ak
                )  # Nuovo valore intermedio minore, calcolato sul nuovo segmento di estremi [ak, bk]

            if (bk - ak) < self.epsilon:
                break

        ### Calcolo del passo ottimo

        lambdaopt = (bk + ak) / 2
        yi = gi.copy()
        for interval in self.t_corr:
            yi[self.t_intervals.index(interval)] = gi[self.t_intervals.index(interval)] * (
                1 - (lambdaopt * (self.grad[self.t_intervals.index(interval) - self.pre_int][0]))
            )

        gi_old = gi.copy()
        alfa = 1 / (self.ite + 1)
        od_new = gi_old.copy()

        for interval in self.t_corr:
            od_new[self.t_intervals.index(interval)] = gi_old[self.t_intervals.index(interval)] + alfa * (
                yi[self.t_intervals.index(interval)] - gi_old[self.t_intervals.index(interval)]
            )
            od_new[self.t_intervals.index(interval)][od_new[self.t_intervals.index(interval)] < 0] = 1

        gi = od_new.copy()
        OD_new = self.OD.copy()

        for interval in self.t_corr:
            ind_zone = 0
            new_m = np.reshape(gi[self.t_intervals.index(interval)], [len(self.ODseed[0].mat), len(self.ODseed[0].mat)])
            for z in self.zone:
                for j in self.zone:
                    pos = self.zone.index(j)
                    OD_new[interval][z, j] = new_m[ind_zone][pos]
                ind_zone += 1

        return OD_new

        """


#     a=4
#     indices=[(a,0),(a,1),(a,2),(a,3),(a,4),(a,5),(a,6),(a,7),(a,8),(a,9),(a,10),(a,11),(a,12),(a,13),(a,14),(a,15),(a,16),(a,17),(a,18),(a,19)]
#     for ind in indices:
#         pd.DataFrame(M.mats[ind].mat.toarray()).to_excel('M_'+str(ind)+'.xlsx')


# for i in range(0,91):
#     for j in range(0,i+1):
#         ind=(i,j)
#         a=pd.DataFrame(M.mats[ind].mat.toarray()).to_excel('M_'+str(ind)+'.xlsx')
