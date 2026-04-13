(() => {
  "use strict";

  const PASSWORD_MIN_LENGTH = 8;
  const STATISTICS_CHART_PALETTE = Object.freeze([
    "#1d4ed8",
    "#ea580c",
    "#0f766e",
    "#be185d",
    "#ca8a04",
    "#dc2626",
    "#0891b2",
    "#7c3aed",
  ]);

  const App = {
    passwordPolicyMessage:
      "La contrasena debe tener al menos 8 caracteres, incluir una letra mayuscula, una minuscula, un numero y un simbolo.",

    state: {
      user: null,
      sessionPoll: null,
      sessionStatus: null,
      sessionWarningHidden: false,
      sidebarOpen: false,
      systemStatus: null,
      offlineDismissed: false,
      saleItems: [],
      products: [],
      backups: [],
      users: [],
      roles: [],
      rolePermissionLabels: {},
      searchResults: [],
      searchTimer: null,
      reportData: null,
      currentSaleDetail: null,
      forecastData: null,
      forecastUi: {
        search: "",
        risk: "all",
        sortBy: "risk_purchase",
      },
      productImageDraft: { mode: "none", dataUrl: "" },
    },
    dom: {},
    charts: {},
    modals: {},

    ensureProductQuickFormStructure() {
      const productsPage = document.getElementById("productsPage");
      if (!productsPage) {
        return;
      }

      let headerRow = productsPage.querySelector(":scope > .products-header");
      if (!headerRow) {
        const directChildren = Array.from(productsPage.children);
        headerRow =
          directChildren.find((child) => {
            if (!(child instanceof HTMLElement)) {
              return false;
            }
            const hasHeading = Boolean(child.querySelector("h2, h4"));
            const hasActionButton = Boolean(
              child.querySelector("#addProductBtn"),
            );
            return hasHeading || hasActionButton;
          }) || null;
      }

      if (!headerRow) {
        headerRow = document.createElement("div");
        headerRow.innerHTML = `
          <div>
            <h2 class="mb-1 module-title">Gestion de productos</h2>
            <p class="module-subtitle mb-0">Administra catalogo, IVA, estado activo e inventario minimo por producto.</p>
          </div>
        `;
        productsPage.insertBefore(
          headerRow,
          productsPage.firstElementChild || null,
        );
      }

      headerRow.classList.add(
        "products-header",
        "module-header",
        "d-flex",
        "flex-wrap",
        "justify-content-between",
        "align-items-center",
        "gap-2",
      );
      headerRow.classList.remove("mb-0");
      if (!headerRow.classList.contains("mb-3")) {
        headerRow.classList.add("mb-3");
      }

      const titleEl = headerRow.querySelector("h2, h4");
      if (!titleEl) {
        const title = document.createElement("h2");
        title.className = "mb-1 module-title";
        title.textContent = "Gestion de productos";
        headerRow.prepend(title);
      } else {
        titleEl.classList.add("module-title");
        if (
          !titleEl.classList.contains("mb-1") &&
          !titleEl.classList.contains("mb-0")
        ) {
          titleEl.classList.add("mb-1");
        }
      }

      let subtitle = headerRow.querySelector(".module-subtitle");
      if (!subtitle) {
        subtitle = document.createElement("p");
        subtitle.className = "module-subtitle mb-0";
        subtitle.textContent =
          "Administra catalogo, IVA, estado activo e inventario minimo por producto.";
        const headingTarget = headerRow.querySelector("h2, h4");
        if (
          headingTarget?.parentElement &&
          headingTarget.parentElement !== headerRow
        ) {
          headingTarget.parentElement.appendChild(subtitle);
        } else if (headingTarget) {
          headingTarget.insertAdjacentElement("afterend", subtitle);
        } else {
          headerRow.prepend(subtitle);
        }
      }

      let actions = headerRow.querySelector(".product-header-actions");
      if (!actions) {
        const existingActions = Array.from(headerRow.children).find((child) => {
          if (!(child instanceof HTMLElement)) {
            return false;
          }
          return Boolean(child.querySelector(".btn"));
        });
        if (existingActions instanceof HTMLElement) {
          actions = existingActions;
          actions.classList.add("product-header-actions");
        } else {
          actions = document.createElement("div");
          actions.className = "d-flex gap-2 product-header-actions";
          const movableChildren = Array.from(headerRow.children).filter(
            (child) => {
              if (!(child instanceof HTMLElement)) {
                return false;
              }
              if (child === actions) {
                return false;
              }
              return child.tagName === "BUTTON" || child.matches(".btn");
            },
          );
          movableChildren.forEach((child) => actions.appendChild(child));
          headerRow.appendChild(actions);
        }
      }

      let modalBtn = document.getElementById("addProductBtn");
      if (!modalBtn) {
        modalBtn = document.createElement("button");
        modalBtn.id = "addProductBtn";
        actions.appendChild(modalBtn);
      } else if (!actions.contains(modalBtn)) {
        actions.appendChild(modalBtn);
      }

      modalBtn.type = "button";
      modalBtn.className = "btn btn-primary permission-gated";
      modalBtn.dataset.permission = "products_manage";
      modalBtn.textContent = "Nuevo producto";
    },

    init() {
      this.cacheDom();
      this.prepareUI();
      this.bindEvents();
      this.checkExistingSession();
    },

    cacheDom() {
      this.ensureProductQuickFormStructure();
      const ids = [
        "loginPage",
        "loginForm",
        "loginError",
        "username",
        "password",
        "togglePassword",
        "togglePasswordIcon",
        "appShell",
        "sidebarPanel",
        "mobileSidebarOverlay",
        "menuToggleBtn",
        "menuCloseBtn",
        "mainContent",
        "userName",
        "userRoleLabel",
        "logoutBtn",
        "topbarGreetingName",
        "topbarDateLabel",
        "sessionWarningBanner",
        "sessionWarningText",
        "sessionKeepAliveBtn",
        "sessionDismissBtn",
        "salesToday",
        "lowStockTotal",
        "criticalStockTotal",
        "totalProducts",
        "missingImagesTotal",
        "popularProducts",
        "lowStockAlerts",
        "paymentMethodsSummary",
        "paymentMethodsList",
        "paymentDateFrom",
        "paymentDateTo",
        "refreshPaymentMethodsBtn",
        "resetPaymentMethodsBtn",
        "productSearch",
        "searchResults",
        "saleItems",
        "recentSalesMessage",
        "refreshRecentSalesBtn",
        "recentSalesTable",
        "saleSubtotal",
        "saleIva",
        "saleIvaRate",
        "saleTotal",
        "paymentMethod",
        "resetSaleBtn",
        "completeSaleBtn",
        "saleMessage",
        "productForm",
        "productFormMessage",
        "productId",
        "productName",
        "productCategory",
        "productPrice",
        "productIvaHint",
        "productIvaPercent",
        "productStock",
        "productMinStock",
        "productImageInput",
        "productImagePreview",
        "productImageClearBtn",
        "productsTable",
        "exportProductsPdfBtn",
        "exportProductsExcelBtn",
        "importProductsBtn",
        "productImportInput",
        "productImportMessage",
        "addProductBtn",
        "saveProductBtn",
        "productFilter",
        "filterProductBtn",
        "ivaPercentInput",
        "saveIvaBtn",
        "ivaConfigMessage",
        "auditDateFrom",
        "auditDateTo",
        "auditActionFilter",
        "auditUserFilter",
        "filterAuditBtn",
        "refreshAuditBtn",
        "auditExportPdfBtn",
        "auditExportExcelBtn",
        "auditSummary",
        "auditTable",
        "minStockFormMessage",
        "minStockProductId",
        "minStockProductName",
        "minStockValue",
        "saveMinStockBtn",
        "addUserBtn",
        "saveUserBtn",
        "userForm",
        "userFormMessage",
        "userId",
        "userUsername",
        "userPassword",
        "userNameInput",
        "userRole",
        "userActive",
        "usersTable",
        "userNewRolePanel",
        "userNewRoleName",
        "userRolePermissionsGrid",
        "reportDateFrom",
        "reportDateTo",
        "generateReportBtn",
        "reportExportPdfBtn",
        "reportExportExcelBtn",
        "reportSummary",
        "salesReportTable",
        "statsDateFrom",
        "statsDateTo",
        "generateStatsBtn",
        "statsExportPdfBtn",
        "statsExportExcelBtn",
        "statisticsEmpty",
        "categoriesPieChart",
        "statisticsSummaryRow",
        "statisticsNote",
        "statsSummaryRevenue",
        "statsSummaryUnits",
        "statsSummaryTopProduct",
        "statsSummaryTopRevenue",
        "statsUnitsTable",
        "statsLegend",
        "statsChartHint",
        "statsChartFocus",
        "forecastHorizonDays",
        "refreshForecastBtn",
        "forecastModelSummary",
        "forecastModelBadges",
        "forecastPeriodInfo",
        "forecastSummary",
        "forecastSearchInput",
        "forecastRiskFilter",
        "forecastSortBy",
        "forecastTable",
        "forecastKpiProducts",
        "forecastKpiActionable",
        "forecastKpiCritical",
        "forecastKpiCoverage",
        "forecastResultCount",
        "forecastQuickAll",
        "forecastQuickCritical",
        "forecastQuickWarning",
        "userProfileInfo",
        "userRoleSummary",
        "userRoleCapabilities",
        "userSessionInfo",
        "offlineBanner",
        "offlineBannerText",
        "offlineBannerDismiss",
        "generateBackupBtn",
        "refreshBackupsBtn",
        "backupMessage",
        "backupsTable",
        "aiChatConversation",
        "aiChatQuestion",
        "aiChatSendBtn",
        "aiChatStatus",
        "postSaleRecommendations",
        "postSaleRecommendationsContent",
        "saleIdHeader",
        "saleDate",
        "saleSubtotalDetail",
        "saleIvaDetail",
        "saleTotalDetail",
        "salePaymentMethod",
        "saleDetailItems",
        "saleRecommendations",
        "saleVoidStatus",
        "saleVoidControls",
        "saleVoidManagerPanel",
        "saleVoidKey",
        "authorizeSaleVoidBtn",
        "saleVoidSellerPanel",
        "voidSaleBtn",
        "saleVoidMessage",
      ];
      ids.forEach((id) => {
        this.dom[id] = document.getElementById(id);
      });
      this.dom.navLinks = Array.from(
        document.querySelectorAll(".sidebar .nav-link"),
      );
      this.dom.permissionGated = Array.from(
        document.querySelectorAll("[data-permission]"),
      );
      this.dom.rolePermissionInputs = Array.from(
        document.querySelectorAll(".role-permission-input"),
      );
      if (window.bootstrap && typeof bootstrap.Modal === "function") {
        const modalIds = {
          product: "productModal",
          minStock: "minStockModal",
          user: "userModal",
          saleDetail: "saleDetailModal",
        };
        Object.entries(modalIds).forEach(([key, id]) => {
          const el = document.getElementById(id);
          if (el) {
            this.modals[key] = new bootstrap.Modal(el);
          }
        });
      }
    },

    prepareUI() {
      if (this.dom.appShell) {
        this.dom.appShell.classList.add("d-none");
        this.dom.appShell.classList.remove("sidebar-open");
      }
      document.body.classList.remove("mobile-menu-open");
      this.state.sidebarOpen = false;
      if (this.dom.sessionWarningBanner) {
        this.dom.sessionWarningBanner.classList.add("d-none");
      }
      if (this.dom.offlineBanner) {
        this.dom.offlineBanner.classList.add("d-none");
      }
      if (this.dom.backupMessage) {
        this.dom.backupMessage.textContent = "";
        this.dom.backupMessage.classList.remove("text-danger");
      }
      if (this.dom.productImportMessage) {
        this.dom.productImportMessage.textContent =
          "Importa un archivo CSV o Excel para crear o actualizar productos en lote.";
        this.dom.productImportMessage.classList.remove("text-danger");
      }
      if (this.dom.backupsTable) {
        this.dom.backupsTable.innerHTML =
          '<tr><td colspan="4" class="text-muted text-center">Sin respaldos cargados.</td></tr>';
        this.applyTableLabels(this.dom.backupsTable);
      }
      if (this.dom.recentSalesTable) {
        this.dom.recentSalesTable.innerHTML =
          '<tr><td colspan="6" class="text-muted text-center">Sin ventas recientes cargadas.</td></tr>';
        this.applyTableLabels(this.dom.recentSalesTable);
      }
      this.state.currentSaleDetail = null;
      this.renderTopbarDateLabel();
      this.state.offlineDismissed = false;
      if (this.dom.loginError) {
        this.dom.loginError.classList.add("d-none");
        this.dom.loginError.textContent = "";
      }
      if (this.dom.reportDateFrom && this.dom.reportDateTo) {
        const today = new Date();
        const lastWeek = new Date(today.getTime() - 6 * 24 * 60 * 60 * 1000);
        this.dom.reportDateFrom.value = this.formatInputDate(lastWeek);
        this.dom.reportDateTo.value = this.formatInputDate(today);
      }
      if (this.dom.statsDateFrom && this.dom.statsDateTo) {
        const today = new Date();
        const lastQuarter = new Date(
          today.getTime() - 89 * 24 * 60 * 60 * 1000,
        );
        this.dom.statsDateFrom.value = this.formatInputDate(lastQuarter);
        this.dom.statsDateTo.value = this.formatInputDate(today);
      }
      this.resetDashboardPaymentRange();
      if (this.dom.auditDateFrom && this.dom.auditDateTo) {
        this.dom.auditDateFrom.value = "";
        this.dom.auditDateTo.value = "";
      }
      if (this.dom.auditSummary) {
        this.dom.auditSummary.textContent = "Sin datos";
      }
      if (this.dom.forecastHorizonDays) {
        this.dom.forecastHorizonDays.value =
          this.dom.forecastHorizonDays.value || "14";
      }
      if (this.dom.forecastModelSummary) {
        this.dom.forecastModelSummary.textContent = "Sin datos del modelo.";
        this.dom.forecastModelSummary.classList.remove("d-none");
      }
      if (this.dom.forecastModelBadges) {
        this.dom.forecastModelBadges.innerHTML = "";
      }
      if (this.dom.forecastModelSummary) {
        this.dom.forecastModelSummary.classList.add("d-none");
        this.dom.forecastModelSummary.textContent = "";
      }
      if (this.dom.forecastPeriodInfo) {
        this.dom.forecastPeriodInfo.textContent = "Periodo: sin calcular.";
      }
      if (this.dom.forecastSummary) {
        this.dom.forecastSummary.textContent = "Sin datos";
      }
      if (this.dom.forecastKpiProducts) {
        this.dom.forecastKpiProducts.textContent = "0";
      }
      if (this.dom.forecastKpiActionable) {
        this.dom.forecastKpiActionable.textContent = "0";
      }
      if (this.dom.forecastKpiCritical) {
        this.dom.forecastKpiCritical.textContent = "0";
      }
      if (this.dom.forecastKpiCoverage) {
        this.dom.forecastKpiCoverage.textContent = "N/D";
      }
      if (this.dom.forecastResultCount) {
        this.dom.forecastResultCount.textContent = "0 resultados";
      }
      if (this.dom.forecastSearchInput) {
        this.dom.forecastSearchInput.value = "";
      }
      if (this.dom.forecastRiskFilter) {
        this.dom.forecastRiskFilter.value = "all";
      }
      if (this.dom.forecastSortBy) {
        this.dom.forecastSortBy.value = "risk_purchase";
      }
      this.updateForecastQuickButtons("all");
      if (this.dom.ivaPercentInput) {
        this.dom.ivaPercentInput.value = "19";
      }
      if (this.dom.ivaConfigMessage) {
        this.dom.ivaConfigMessage.textContent =
          "Aplica para precios y nuevas ventas.";
        this.dom.ivaConfigMessage.classList.remove("text-danger");
      }
      if (this.dom.criticalStockTotal) {
        this.dom.criticalStockTotal.textContent = "0";
      }
      if (this.dom.missingImagesTotal) {
        this.dom.missingImagesTotal.textContent = "0";
      }
    },

    updateForecastQuickButtons(activeRisk = "all") {
      const normalizedRisk = String(activeRisk || "all").toLowerCase();
      const quickButtons = [
        this.dom.forecastQuickAll,
        this.dom.forecastQuickCritical,
        this.dom.forecastQuickWarning,
      ];
      quickButtons.forEach((btn) => {
        if (!btn) {
          return;
        }
        const btnRisk = String(btn.dataset.risk || "").toLowerCase();
        const isActive = btnRisk === normalizedRisk;
        btn.classList.toggle("active", isActive);
        btn.setAttribute("aria-pressed", isActive ? "true" : "false");
      });
    },

    setForecastQuickFilter(riskValue, options = {}) {
      const requested = String(riskValue || "all").toLowerCase();
      const allowed = new Set([
        "all",
        "critico",
        "alerta",
        "estable",
        "sin_dato",
      ]);
      const normalizedRisk = allowed.has(requested) ? requested : "all";
      if (this.dom.forecastRiskFilter) {
        this.dom.forecastRiskFilter.value = normalizedRisk;
      }
      this.updateForecastQuickButtons(normalizedRisk);
      if (options.render !== false) {
        this.renderDemandForecast(this.state.forecastData);
      }
    },

    bindEvents() {
      if (this.dom.loginForm) {
        this.dom.loginForm.addEventListener("submit", (evt) => {
          evt.preventDefault();
          this.handleLoginSubmit();
        });
      }
      this.setupPasswordToggle();
      this.dom.logoutBtn?.addEventListener("click", (evt) => {
        evt.preventDefault();
        this.logout();
      });
      this.dom.offlineBannerDismiss?.addEventListener("click", (evt) => {
        evt.preventDefault();
        this.state.offlineDismissed = true;
        this.dom.offlineBanner?.classList.add("d-none");
      });
      this.dom.menuToggleBtn?.addEventListener("click", (evt) => {
        evt.preventDefault();
        this.toggleSidebarMenu();
      });
      this.dom.menuCloseBtn?.addEventListener("click", (evt) => {
        evt.preventDefault();
        this.closeSidebarMenu();
      });
      this.dom.mobileSidebarOverlay?.addEventListener("click", (evt) => {
        evt.preventDefault();
        this.closeSidebarMenu();
      });
      window.addEventListener("resize", () => {
        this.syncSidebarForViewport();
      });
      document.addEventListener("keydown", (evt) => {
        if (evt.key === "Escape") {
          this.closeSidebarMenu();
        }
      });
      if (this.dom.navLinks) {
        this.dom.navLinks.forEach((link) => {
          link.addEventListener("click", (evt) => {
            evt.preventDefault();
            const page = link.dataset.page;
            if (page) {
              this.setActivePage(page);
            }
          });
        });
      }
      this.dom.sessionKeepAliveBtn?.addEventListener("click", (evt) => {
        evt.preventDefault();
        this.keepAliveSession();
      });
      this.dom.sessionDismissBtn?.addEventListener("click", (evt) => {
        evt.preventDefault();
        this.state.sessionWarningHidden = true;
        this.dom.sessionWarningBanner?.classList.add("d-none");
      });
      this.dom.generateBackupBtn?.addEventListener("click", (evt) => {
        evt.preventDefault();
        this.generateManualBackup();
      });
      this.dom.refreshBackupsBtn?.addEventListener("click", (evt) => {
        evt.preventDefault();
        this.loadBackupsList();
      });
      this.dom.productSearch?.addEventListener("input", () => {
        this.queueSearch(this.dom.productSearch.value.trim());
      });
      this.dom.searchResults?.addEventListener("click", (evt) => {
        const target = evt.target.closest('[data-action="add"]');
        if (!target) {
          return;
        }
        const id = Number(target.dataset.id);
        const product = (this.state.searchResults || []).find(
          (item) => item.id === id,
        );
        if (product) {
          this.addSaleItem(product);
        }
      });
      if (this.dom.saleItems) {
        this.dom.saleItems.addEventListener("input", (evt) => {
          const input = evt.target;
          if (input.dataset.action === "quantity") {
            const id = Number(input.dataset.id);
            let quantity = Number(input.value);
            if (!Number.isFinite(quantity) || quantity <= 0) {
              quantity = 1;
            }
            this.updateSaleItemQuantity(id, quantity);
          }
        });
        this.dom.saleItems.addEventListener("click", (evt) => {
          const btn = evt.target.closest('[data-action="remove"]');
          if (!btn) {
            return;
          }
          const id = Number(btn.dataset.id);
          this.removeSaleItem(id);
        });
      }
      this.dom.resetSaleBtn?.addEventListener("click", (evt) => {
        evt.preventDefault();
        this.resetSale();
      });
      this.dom.completeSaleBtn?.addEventListener("click", (evt) => {
        evt.preventDefault();
        this.completeSale();
      });
      this.dom.addProductBtn?.addEventListener("click", () =>
        this.openProductModal(),
      );
      this.dom.exportProductsPdfBtn?.addEventListener("click", (evt) => {
        evt.preventDefault();
        this.exportProducts("pdf");
      });
      this.dom.exportProductsExcelBtn?.addEventListener("click", (evt) => {
        evt.preventDefault();
        this.exportProducts("excel");
      });
      this.dom.importProductsBtn?.addEventListener("click", (evt) => {
        evt.preventDefault();
        this.dom.productImportInput?.click();
      });
      this.dom.productImportInput?.addEventListener("change", (evt) => {
        const input = evt.target;
        if (input?.files?.length) {
          this.importProducts(input.files[0]);
        }
      });
      this.dom.saveProductBtn?.addEventListener("click", () =>
        this.saveProduct(),
      );
      this.dom.productImageInput?.addEventListener("change", (evt) =>
        this.handleProductImageSelected(evt),
      );
      this.dom.productImageClearBtn?.addEventListener("click", (evt) => {
        evt.preventDefault();
        this.clearProductImageSelection();
      });
      this.dom.productName?.addEventListener("input", () => {
        if (this.state.productImageDraft?.mode !== "set") {
          const label = this.dom.productName?.value || "Producto";
          const fallback = this.buildDefaultProductImage(label);
          if (this.state.productImageDraft?.mode === "clear") {
            this.updateProductImagePreview(fallback);
          } else if (
            !this.dom.productImagePreview?.src ||
            this.dom.productImagePreview.src.startsWith("data:image/svg+xml")
          ) {
            this.updateProductImagePreview(fallback);
          }
        }
      });
      this.dom.productsTable?.addEventListener("click", (evt) => {
        const actionEl = evt.target.closest("[data-action]");
        if (!actionEl) {
          return;
        }
        const row = actionEl.closest("tr");
        const id = Number(row?.dataset.id);
        const product = this.state.products.find((item) => item.id === id);
        if (actionEl.dataset.action === "edit") {
          this.openProductModal(product || null);
        } else if (actionEl.dataset.action === "min") {
          this.openMinStockModal(product || null);
        } else if (actionEl.dataset.action === "delete") {
          this.deleteProduct(id);
        } else if (actionEl.dataset.action === "toggle-state") {
          const active = actionEl.dataset.active === "1";
          this.setProductActive(id, !active);
        }
      });
      this.dom.backupsTable?.addEventListener("click", (evt) => {
        const actionEl = evt.target.closest("[data-action]");
        if (!actionEl) {
          return;
        }
        const filename = actionEl.dataset.filename || "";
        if (!filename) {
          return;
        }
        if (actionEl.dataset.action === "restore") {
          this.restoreBackup(filename);
        }
      });
      this.dom.filterProductBtn?.addEventListener("click", () => {
        this.loadProducts?.(this.dom.productFilter?.value.trim() || "");
        this.queueSearch?.(this.dom.productSearch?.value.trim() || "");
      });
      this.dom.saveIvaBtn?.addEventListener("click", (evt) => {
        evt.preventDefault();
        this.saveIvaConfig();
      });
      this.dom.productFilter?.addEventListener("keypress", (evt) => {
        if (evt.key === "Enter") {
          evt.preventDefault();
          this.loadProducts(this.dom.productFilter.value.trim());
        }
      });
      this.dom.filterAuditBtn?.addEventListener("click", (evt) => {
        evt.preventDefault();
        this.loadAuditTrail();
      });
      this.dom.refreshAuditBtn?.addEventListener("click", (evt) => {
        evt.preventDefault();
        this.loadAuditTrail();
      });
      this.dom.auditExportPdfBtn?.addEventListener("click", (evt) => {
        evt.preventDefault();
        this.exportAuditReport("pdf");
      });
      this.dom.auditExportExcelBtn?.addEventListener("click", (evt) => {
        evt.preventDefault();
        this.exportAuditReport("excel");
      });
      this.dom.saveMinStockBtn?.addEventListener("click", () =>
        this.saveMinStock(),
      );
      this.dom.addUserBtn?.addEventListener("click", () =>
        this.openUserModal(),
      );
      this.dom.saveUserBtn?.addEventListener("click", () => this.saveUser());
      this.dom.userRole?.addEventListener("change", () =>
        this.toggleNewRolePanel(),
      );
      this.dom.usersTable?.addEventListener("click", (evt) => {
        const actionEl = evt.target.closest("[data-action]");
        if (!actionEl) {
          return;
        }
        const row = actionEl.closest("tr");
        const id = Number(row?.dataset.id);
        if (!id) {
          return;
        }
        if (actionEl.dataset.action === "edit") {
          const user = (this.state.users || []).find((item) => item.id === id);
          this.openUserModal(user || null);
        } else if (actionEl.dataset.action === "toggle") {
          const active = actionEl.dataset.active === "1";
          this.toggleUserActive(id, !active);
        }
      });
      this.dom.generateReportBtn?.addEventListener("click", (evt) => {
        evt.preventDefault();
        this.generateReport();
      });
      this.dom.refreshPaymentMethodsBtn?.addEventListener("click", (evt) => {
        evt.preventDefault();
        this.applyDashboardPaymentFilters();
      });
      this.dom.resetPaymentMethodsBtn?.addEventListener("click", async (evt) => {
        evt.preventDefault();
        this.resetDashboardPaymentRange();
        await this.loadDashboard({
          button: this.dom.resetPaymentMethodsBtn,
        });
      });
      [this.dom.paymentDateFrom, this.dom.paymentDateTo].forEach((input) => {
        input?.addEventListener("keydown", (evt) => {
          if (evt.key === "Enter") {
            evt.preventDefault();
            this.applyDashboardPaymentFilters();
          }
        });
      });
      this.dom.reportExportPdfBtn?.addEventListener("click", (evt) => {
        evt.preventDefault();
        this.exportSalesReport("pdf");
      });
      this.dom.reportExportExcelBtn?.addEventListener("click", (evt) => {
        evt.preventDefault();
        this.exportSalesReport("excel");
      });
      this.dom.refreshRecentSalesBtn?.addEventListener("click", (evt) => {
        evt.preventDefault();
        this.loadRecentSales();
      });
      this.dom.recentSalesTable?.addEventListener("click", (evt) => {
        const btn = evt.target.closest('[data-action="detail"]');
        if (!btn) {
          return;
        }
        const row = btn.closest("tr");
        const id = Number(row?.dataset.id);
        if (id) {
          this.openSaleDetail(id);
        }
      });
      this.dom.forecastSearchInput?.addEventListener("input", () =>
        this.renderDemandForecast(this.state.forecastData),
      );
      this.dom.forecastRiskFilter?.addEventListener("change", () => {
        this.setForecastQuickFilter(
          this.dom.forecastRiskFilter?.value || "all",
        );
      });
      this.dom.forecastSortBy?.addEventListener("change", () =>
        this.renderDemandForecast(this.state.forecastData),
      );
      [
        this.dom.forecastQuickAll,
        this.dom.forecastQuickCritical,
        this.dom.forecastQuickWarning,
      ].forEach((btn) => {
        btn?.addEventListener("click", (evt) => {
          evt.preventDefault();
          this.setForecastQuickFilter(btn.dataset.risk || "all");
        });
      });
      this.dom.salesReportTable?.addEventListener("click", (evt) => {
        const btn = evt.target.closest('[data-action="detail"]');
        if (!btn) {
          return;
        }
        const row = btn.closest("tr");
        const id = Number(row?.dataset.id);
        if (id) {
          this.openSaleDetail(id);
        }
      });
      this.dom.authorizeSaleVoidBtn?.addEventListener("click", (evt) => {
        evt.preventDefault();
        this.authorizeCurrentSaleVoid();
      });
      this.dom.voidSaleBtn?.addEventListener("click", (evt) => {
        evt.preventDefault();
        this.disableCurrentSale();
      });
      this.dom.generateStatsBtn?.addEventListener("click", (evt) => {
        evt.preventDefault();
        this.generateStats();
      });
      this.dom.statsExportPdfBtn?.addEventListener("click", (evt) => {
        evt.preventDefault();
        this.exportStatsReport("pdf");
      });
      this.dom.statsExportExcelBtn?.addEventListener("click", (evt) => {
        evt.preventDefault();
        this.exportStatsReport("excel");
      });
      this.dom.refreshForecastBtn?.addEventListener("click", (evt) => {
        evt.preventDefault();
        this.loadDemandForecast();
      });
      this.dom.aiChatSendBtn?.addEventListener("click", (evt) => {
        evt.preventDefault();
        this.handleAiChat();
      });
      this.dom.aiChatQuestion?.addEventListener("keydown", (evt) => {
        if (evt.key === "Enter" && (evt.ctrlKey || evt.metaKey)) {
          evt.preventDefault();
          this.handleAiChat();
        }
      });
    },

    setupPasswordToggle() {
      const passwordInput = this.dom.password;
      const toggleBtn = this.dom.togglePassword;
      if (!passwordInput || !toggleBtn) {
        return;
      }
      const icon = this.dom.togglePasswordIcon;
      let isForcedVisible = false;

      const applyVisibility = (visible) => {
        const isVisible = Boolean(visible);
        passwordInput.type = isVisible ? "text" : "password";
        toggleBtn.classList.toggle("active", isVisible);
        toggleBtn.setAttribute(
          "aria-label",
          isVisible ? "Ocultar contrasena" : "Mostrar contrasena",
        );
        toggleBtn.setAttribute("aria-pressed", String(isVisible));
        if (icon) {
          icon.classList.toggle("bi-eye", !isVisible);
          icon.classList.toggle("bi-eye-slash", isVisible);
        }
      };

      const focusPassword = () => {
        passwordInput.focus();
        const valueLength = passwordInput.value.length;
        if (typeof passwordInput.setSelectionRange === "function") {
          passwordInput.setSelectionRange(valueLength, valueLength);
        }
      };

      const showWhilePressed = () => {
        if (isForcedVisible) {
          return;
        }
        applyVisibility(true);
      };

      const hideWhilePressed = () => {
        if (isForcedVisible) {
          return;
        }
        applyVisibility(false);
      };

      toggleBtn.addEventListener("click", (evt) => {
        evt.preventDefault();
        isForcedVisible = !isForcedVisible;
        applyVisibility(isForcedVisible);
        focusPassword();
      });
      toggleBtn.addEventListener("mousedown", (evt) => {
        if (evt.button !== 0) {
          return;
        }
        showWhilePressed();
      });
      toggleBtn.addEventListener("mouseup", hideWhilePressed);
      toggleBtn.addEventListener("mouseleave", hideWhilePressed);
      toggleBtn.addEventListener(
        "touchstart",
        (evt) => {
          evt.preventDefault();
          showWhilePressed();
        },
        { passive: false },
      );
      toggleBtn.addEventListener("touchend", hideWhilePressed);
      toggleBtn.addEventListener("touchcancel", hideWhilePressed);

      applyVisibility(false);
    },

    async fetchJson(url, options = {}) {
      const isFormData =
        typeof FormData !== "undefined" && options.body instanceof FormData;
      const config = {
        method: options.method || "GET",
        headers: {
          Accept: "application/json",
          ...(!isFormData && options.body
            ? { "Content-Type": "application/json" }
            : {}),
          ...(options.headers || {}),
        },
        credentials: "include",
      };
      if (options.body !== undefined) {
        if (isFormData) {
          config.body = options.body;
        } else {
          config.body =
            typeof options.body === "string"
              ? options.body
              : JSON.stringify(options.body);
        }
      }
      const response = await fetch(url, config);
      const contentType = response.headers.get("content-type") || "";
      const dataSource = response.headers.get("x-data-source");
      if (dataSource === "offline-cache") {
        const currentStatus = this.state.systemStatus || {};
        const merged = { ...currentStatus, offline: true };
        this.state.systemStatus = merged;
        this.renderOfflineStatus?.(merged);
      } else if (
        this.state.systemStatus?.offline &&
        dataSource !== "offline-cache"
      ) {
        const merged = { ...this.state.systemStatus, offline: false };
        this.state.systemStatus = merged;
        this.renderOfflineStatus?.(merged);
      }
      let payload = null;
      if (contentType.includes("application/json")) {
        payload = await response.json();
      } else if (response.status !== 204) {
        payload = await response.text();
      }
      if (!response.ok) {
        const error = new Error(
          payload?.error || response.statusText || "Error en la solicitud",
        );
        error.status = response.status;
        error.payload = payload;
        throw error;
      }
      return payload;
    },

    parseContentDispositionFilename(contentDisposition, fallback = "reporte") {
      if (!contentDisposition) {
        return fallback;
      }
      const encodedMatch = contentDisposition.match(
        /filename\*=UTF-8''([^;]+)/i,
      );
      if (encodedMatch && encodedMatch[1]) {
        try {
          return decodeURIComponent(
            encodedMatch[1].replace(/["']/g, "").trim(),
          );
        } catch (error) {
          return encodedMatch[1].replace(/["']/g, "").trim() || fallback;
        }
      }
      const simpleMatch = contentDisposition.match(/filename="?([^"]+)"?/i);
      if (simpleMatch && simpleMatch[1]) {
        return simpleMatch[1].trim() || fallback;
      }
      return fallback;
    },

    async downloadApiFile(url, fallbackName = "reporte") {
      const response = await fetch(url, {
        method: "GET",
        credentials: "include",
      });
      const contentType = response.headers.get("content-type") || "";
      if (!response.ok || contentType.includes("application/json")) {
        let payload = null;
        if (contentType.includes("application/json")) {
          try {
            payload = await response.json();
          } catch (error) {
            payload = null;
          }
        }
        const message =
          payload?.error ||
          `No se pudo exportar el archivo (HTTP ${response.status}).`;
        const exportError = new Error(message);
        exportError.status = response.status;
        exportError.payload = payload;
        throw exportError;
      }
      const blob = await response.blob();
      const filename = this.parseContentDispositionFilename(
        response.headers.get("content-disposition"),
        fallbackName,
      );
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(objectUrl);
    },

    setButtonBusy(button, busy) {
      if (!button) {
        return;
      }
      if (busy) {
        const currentCount = Number(button.dataset.busyCount || "0");
        if (currentCount <= 0) {
          button.dataset.prevText = button.textContent;
          button.textContent = "Procesando...";
        }
        button.dataset.busyCount = String(currentCount + 1);
        button.disabled = true;
        return;
      }
      const currentCount = Number(button.dataset.busyCount || "0");
      if (currentCount <= 1) {
        button.disabled = false;
        if (button.dataset.prevText) {
          button.textContent = button.dataset.prevText;
          delete button.dataset.prevText;
        }
        delete button.dataset.busyCount;
      } else {
        button.dataset.busyCount = String(currentCount - 1);
      }
    },

    setAriaBusy(element, busy) {
      if (!element) {
        return;
      }
      element.setAttribute("aria-busy", busy ? "true" : "false");
    },

    getTableLabels(tbody) {
      if (!tbody || !tbody.dataset || !tbody.dataset.labels) {
        return [];
      }
      return tbody.dataset.labels.split("|").map((label) => label.trim());
    },

    showTableSkeleton(tbody, rows = 3) {
      if (!tbody) {
        return;
      }
      const labels = this.getTableLabels(tbody);
      const table = tbody.closest("table");
      const columnCount =
        labels.length ||
        (table ? table.querySelectorAll("thead th").length : 1) ||
        1;
      const skeletonRows = [];
      for (let rowIndex = 0; rowIndex < rows; rowIndex += 1) {
        const cells = [];
        for (let colIndex = 0; colIndex < columnCount; colIndex += 1) {
          const label = labels[colIndex];
          const labelAttr = label ? ` data-label="${this.escape(label)}"` : "";
          cells.push(
            `<td${labelAttr}><span class="skeleton-line" aria-hidden="true"></span></td>`,
          );
        }
        skeletonRows.push(`<tr class="skeleton-row">${cells.join("")}</tr>`);
      }
      tbody.innerHTML = skeletonRows.join("");
      if (table) {
        table.setAttribute("aria-busy", "true");
      }
    },

    clearTableSkeleton(tbody) {
      if (!tbody) {
        return;
      }
      const table = tbody.closest("table");
      if (table) {
        table.setAttribute("aria-busy", "false");
      }
    },

    applyTableLabels(tbody) {
      if (!tbody) {
        return;
      }
      const labels = this.getTableLabels(tbody);
      if (!labels.length) {
        return;
      }
      tbody.querySelectorAll("tr").forEach((row) => {
        let cellIndex = 0;
        row.querySelectorAll("td").forEach((cell) => {
          if (cell.colSpan && cell.colSpan > 1) {
            cell.removeAttribute("data-label");
            return;
          }
          const label = labels[cellIndex] || "";
          if (label) {
            cell.setAttribute("data-label", label);
          } else {
            cell.removeAttribute("data-label");
          }
          cellIndex += 1;
        });
      });
    },

    setAlert(element, message, type = "info") {
      if (!element) {
        return;
      }
      element.className = `alert alert-${type}`;
      element.setAttribute("role", "alert");
      element.setAttribute("aria-live", "assertive");
      element.setAttribute("aria-atomic", "true");
      element.textContent = message;
      element.classList.remove("d-none");
    },

    escape(value) {
      if (value == null) {
        return "";
      }
      return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
    },

    formatCurrency(value) {
      const number = Number(value) || 0;
      return new Intl.NumberFormat("es-CO", {
        style: "currency",
        currency: "COP",
        minimumFractionDigits: 0,
        maximumFractionDigits: 0,
      }).format(number);
    },

    formatNumber(value) {
      const number = Number(value) || 0;
      return new Intl.NumberFormat("es-CO").format(number);
    },

    formatDecimal(value, maxFractionDigits = 2) {
      const number = Number(value);
      if (!Number.isFinite(number)) {
        return this.formatNumber(0);
      }
      return new Intl.NumberFormat("es-CO", {
        minimumFractionDigits: 0,
        maximumFractionDigits: Math.max(
          0,
          Math.min(4, Number(maxFractionDigits) || 2),
        ),
      }).format(number);
    },

    hexToRgba(value, alpha = 1) {
      const safeAlpha = Math.max(0, Math.min(1, Number(alpha) || 0));
      const hex = String(value || "")
        .trim()
        .replace(/^#/, "");
      if (!/^[0-9a-f]{6}$/i.test(hex)) {
        return `rgba(47, 88, 231, ${safeAlpha})`;
      }
      const red = Number.parseInt(hex.slice(0, 2), 16);
      const green = Number.parseInt(hex.slice(2, 4), 16);
      const blue = Number.parseInt(hex.slice(4, 6), 16);
      return `rgba(${red}, ${green}, ${blue}, ${safeAlpha})`;
    },

    buildDefaultProductImage(label = "Producto") {
      const text =
        String(label || "Producto")
          .trim()
          .slice(0, 20) || "Producto";
      const initials =
        text
          .split(/\s+/)
          .filter(Boolean)
          .slice(0, 2)
          .map((chunk) => chunk[0].toUpperCase())
          .join("") || "P";
      const svg = `
        <svg xmlns="http://www.w3.org/2000/svg" width="140" height="110" viewBox="0 0 140 110">
          <defs>
            <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stop-color="#3f68e9"/>
              <stop offset="100%" stop-color="#7a93f6"/>
            </linearGradient>
          </defs>
          <rect width="140" height="110" rx="14" fill="url(#g)"/>
          <rect x="8" y="8" width="124" height="94" rx="10" fill="rgba(255,255,255,0.12)"/>
          <text x="70" y="58" text-anchor="middle" font-size="30" font-family="Arial" fill="#fff" font-weight="700">${this.escape(initials)}</text>
          <text x="70" y="80" text-anchor="middle" font-size="11" font-family="Arial" fill="#edf2ff">Sin imagen</text>
        </svg>
      `.trim();
      return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
    },

    resolveProductImageUrl(product) {
      const image = String(
        product?.imagen_url || product?.image_url || product?.image || "",
      ).trim();
      if (
        image &&
        (image.startsWith("data:image/") ||
          image.startsWith("http://") ||
          image.startsWith("https://"))
      ) {
        return image;
      }
      return this.buildDefaultProductImage(product?.nombre || "Producto");
    },

    updateProductImagePreview(url) {
      if (!this.dom.productImagePreview) {
        return;
      }
      this.dom.productImagePreview.src =
        url || this.buildDefaultProductImage("Producto");
    },

    resetProductImageDraft(product = null) {
      this.state.productImageDraft = { mode: "none", dataUrl: "" };
      if (this.dom.productImageInput) {
        this.dom.productImageInput.value = "";
      }
      this.updateProductImagePreview(this.resolveProductImageUrl(product));
    },

    clearProductImageSelection() {
      this.state.productImageDraft = { mode: "clear", dataUrl: "" };
      if (this.dom.productImageInput) {
        this.dom.productImageInput.value = "";
      }
      this.updateProductImagePreview(
        this.buildDefaultProductImage(
          this.dom.productName?.value || "Producto",
        ),
      );
    },

    async handleProductImageSelected(evt) {
      const input = evt?.target;
      if (!input || !input.files || !input.files.length) {
        return;
      }
      const file = input.files[0];
      const maxBytes = 900 * 1024;
      if (file.size > maxBytes) {
        this.setAlert(
          this.dom.productFormMessage,
          "La imagen supera 900 KB. Usa una imagen más liviana.",
          "warning",
        );
        input.value = "";
        return;
      }
      const dataUrl = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result || ""));
        reader.onerror = () => reject(new Error("No se pudo leer la imagen."));
        reader.readAsDataURL(file);
      }).catch((error) => {
        const message = error?.message || "No se pudo cargar la imagen.";
        this.setAlert(this.dom.productFormMessage, message, "danger");
        return "";
      });
      if (!dataUrl) {
        return;
      }
      this.state.productImageDraft = { mode: "set", dataUrl };
      this.updateProductImagePreview(dataUrl);
      this.dom.productFormMessage?.classList.add("d-none");
    },

    roundMoney(value) {
      const number = Number(value);
      if (!Number.isFinite(number)) {
        return 0;
      }
      return Math.round(number * 100) / 100;
    },

    getCurrentIvaRate() {
      const raw = Number(this.state.user?.iva_percent);
      if (!Number.isFinite(raw)) {
        return 19;
      }
      return Math.max(0, Math.min(100, raw));
    },

    getProductBasePrice(product) {
      return Number(product?.precio_base ?? product?.precio ?? product?.price ?? 0);
    },

    getProductIvaRate(product) {
      const raw = Number(
        product?.iva_porcentaje ?? product?.iva_percent ?? this.getCurrentIvaRate(),
      );
      if (!Number.isFinite(raw)) {
        return this.getCurrentIvaRate();
      }
      return Math.max(0, Math.min(100, raw));
    },

    getProductIvaValue(product) {
      const raw = Number(product?.iva_valor);
      if (Number.isFinite(raw)) {
        return raw;
      }
      const priceBase = this.getProductBasePrice(product);
      const ivaRate = this.getProductIvaRate(product);
      return this.roundMoney((priceBase * ivaRate) / 100);
    },

    getProductPriceWithIva(product) {
      const raw = Number(product?.precio_con_iva);
      if (Number.isFinite(raw)) {
        return raw;
      }
      return this.roundMoney(
        this.getProductBasePrice(product) + this.getProductIvaValue(product),
      );
    },

    getAllowedPaymentMethods() {
      const current = this.state.user?.allowed_payment_methods;
      if (Array.isArray(current) && current.length) {
        return current
          .map((entry) =>
            String(entry || "")
              .trim()
              .toLowerCase(),
          )
          .filter(Boolean);
      }
      return ["efectivo", "nequi", "daviplata", "transferencia"];
    },

    paymentMethodLabel(code) {
      const normalized = String(code || "")
        .trim()
        .toLowerCase();
      const labels = {
        efectivo: "Efectivo",
        nequi: "Nequi",
        daviplata: "Daviplata",
        transferencia: "Transferencia",
      };
      return labels[normalized] || normalized.toUpperCase();
    },

    renderPaymentMethodOptions() {
      if (!this.dom.paymentMethod) {
        return;
      }
      const methods = this.getAllowedPaymentMethods();
      if (!methods.length) {
        this.dom.paymentMethod.innerHTML =
          '<option value="efectivo">Efectivo</option>';
        return;
      }
      this.dom.paymentMethod.innerHTML = methods
        .map(
          (code) =>
            `<option value="${this.escape(code)}">${this.escape(this.paymentMethodLabel(code))}</option>`,
        )
        .join("");
    },

    formatDateTime(value) {
      if (!value) {
        return "--";
      }
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) {
        return value;
      }
      return date.toLocaleString("es-CO", {
        dateStyle: "short",
        timeStyle: "short",
      });
    },

    formatDateOnly(value) {
      if (!value) {
        return "--";
      }
      const source =
        typeof value === "string" && !value.includes("T")
          ? `${value}T00:00:00`
          : value;
      const date = new Date(source);
      if (Number.isNaN(date.getTime())) {
        return value;
      }
      return date.toLocaleDateString("es-CO");
    },

    formatForecastRunoutLabel(value) {
      if (!value) {
        return "";
      }
      const source =
        typeof value === "string" && !value.includes("T")
          ? `${value}T00:00:00`
          : value;
      const runoutDate = new Date(source);
      if (Number.isNaN(runoutDate.getTime())) {
        return `Agota aprox: ${this.escape(String(value))}`;
      }
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      if (runoutDate < today) {
        return "Agota aprox: hoy";
      }
      return `Agota aprox: ${this.formatDateOnly(value)}`;
    },

    renderTopbarDateLabel() {
      if (!this.dom.topbarDateLabel) {
        return;
      }
      const now = new Date();
      this.dom.topbarDateLabel.textContent = now.toLocaleDateString("es-CO", {
        day: "numeric",
        month: "long",
        year: "numeric",
      });
    },

    formatInputDate(date) {
      const yyyy = date.getFullYear();
      const mm = String(date.getMonth() + 1).padStart(2, "0");
      const dd = String(date.getDate()).padStart(2, "0");
      return `${yyyy}-${mm}-${dd}`;
    },

    resetDashboardPaymentRange() {
      if (!this.dom.paymentDateFrom || !this.dom.paymentDateTo) {
        return;
      }
      const today = new Date();
      const lastQuarter = new Date(
        today.getTime() - 89 * 24 * 60 * 60 * 1000,
      );
      this.dom.paymentDateFrom.value = this.formatInputDate(lastQuarter);
      this.dom.paymentDateTo.value = this.formatInputDate(today);
    },

    async applyDashboardPaymentFilters() {
      const from = this.dom.paymentDateFrom?.value || "";
      const to = this.dom.paymentDateTo?.value || "";
      if (!from || !to) {
        window.alert(
          "Selecciona un rango de fechas para consultar los metodos de pago.",
        );
        return;
      }
      if (new Date(from) > new Date(to)) {
        window.alert('La fecha "Desde" no puede ser mayor que "Hasta".');
        return;
      }
      await this.loadDashboard({
        from,
        to,
        button: this.dom.refreshPaymentMethodsBtn,
      });
    },

    secondsToHms(seconds) {
      if (!Number.isFinite(seconds)) {
        return "--";
      }
      const hrs = Math.floor(seconds / 3600);
      const mins = Math.floor((seconds % 3600) / 60);
      const secs = seconds % 60;
      const parts = [];
      if (hrs) {
        parts.push(`${hrs}h`);
      }
      if (mins || hrs) {
        parts.push(`${mins}m`);
      }
      parts.push(`${secs}s`);
      return parts.join(" ");
    },

    getRolePermissionDefaults(rawRole = "") {
      const keys = [
        "dashboard_view",
        "sales_view",
        "sales_create",
        "products_view",
        "products_manage",
        "reports_view",
        "statistics_view",
        "users_manage",
        "audit_view",
        "sessions_manage",
        "backups_manage",
        "ai_chat",
      ];
      const role = String(rawRole || "")
        .trim()
        .toLowerCase();
      const permissions = {};
      keys.forEach((key) => {
        permissions[key] = false;
      });
      if (role === "admin") {
        keys.forEach((key) => {
          permissions[key] = true;
        });
        return permissions;
      }
      if (role === "gerente") {
        [
          "dashboard_view",
          "sales_view",
          "sales_create",
          "products_view",
          "products_manage",
          "reports_view",
          "statistics_view",
          "users_manage",
          "backups_manage",
          "ai_chat",
        ].forEach((key) => {
          permissions[key] = true;
        });
      } else if (role === "vendedor") {
        [
          "dashboard_view",
          "sales_view",
          "sales_create",
          "products_view",
          "ai_chat",
        ].forEach((key) => {
          permissions[key] = true;
        });
      } else if (role === "auditador") {
        permissions.audit_view = true;
      }
      return permissions;
    },

    normalizePermissions(rawPermissions = {}, rawRole = null) {
      const keys = [
        "dashboard_view",
        "sales_view",
        "sales_create",
        "products_view",
        "products_manage",
        "reports_view",
        "statistics_view",
        "users_manage",
        "audit_view",
        "sessions_manage",
        "backups_manage",
        "ai_chat",
      ];
      const resolvedRole =
        rawRole ?? (this.state.user ? this.state.user.role : "");
      const role = String(resolvedRole || "")
        .trim()
        .toLowerCase();
      const hasExplicitPermissions =
        rawPermissions && typeof rawPermissions === "object"
          ? keys.some((key) =>
              Object.prototype.hasOwnProperty.call(rawPermissions, key),
            )
          : false;
      const permissions = this.getRolePermissionDefaults(role);
      if (hasExplicitPermissions) {
        keys.forEach((key) => {
          permissions[key] = Boolean(rawPermissions[key]);
        });
      }
      if (role === "admin") {
        keys.forEach((key) => {
          permissions[key] = true;
        });
      }
      return permissions;
    },

    can(permissionKey) {
      if (!this.state.user) {
        return false;
      }
      const permissions = this.normalizePermissions(
        this.state.user.permissions || {},
      );
      return Boolean(permissions[permissionKey]);
    },

    canAny(permissionList = []) {
      const list = Array.isArray(permissionList)
        ? permissionList
        : [permissionList];
      return list.some((permission) => this.can(permission));
    },
  };

  Object.assign(App, {
    showLogin(message) {
      if (this.dom.appShell) {
        this.dom.appShell.classList.add("d-none");
        this.dom.appShell.setAttribute("hidden", "hidden");
      }
      this.setSidebarMenuOpen(false);
      this.dom.loginPage?.classList.remove("d-none");
      this.dom.loginPage?.removeAttribute("hidden");
      this.resetAiChatHistory();
      if (message) {
        this.showLoginError(message);
      }
      this.dom.username?.focus();
    },

    showLoginError(message) {
      if (!this.dom.loginError) {
        return;
      }
      this.dom.loginError.textContent = message;
      this.dom.loginError.classList.remove("d-none");
    },

    clearLoginError() {
      if (!this.dom.loginError) {
        return;
      }
      this.dom.loginError.textContent = "";
      this.dom.loginError.classList.add("d-none");
    },

    async handleLoginSubmit() {
      const username = this.dom.username?.value.trim();
      const password = this.dom.password?.value || "";
      if (!username || !password) {
        this.showLoginError("Ingresa usuario y contrasena.");
        return;
      }
      try {
        this.clearLoginError();
        const submitBtn = this.dom.loginForm?.querySelector(
          'button[type="submit"]',
        );
        this.setButtonBusy(submitBtn, true);
        const data = await this.fetchJson("/api/login", {
          method: "POST",
          body: { username, password },
        });
        if (data?.success && data.user) {
          if (this.dom.username) {
            this.dom.username.value = "";
          }
          if (this.dom.password) {
            this.dom.password.value = "";
          }
          this.onAuthenticated(data.user);
        } else {
          this.showLoginError("No se pudo iniciar sesion.");
        }
      } catch (error) {
        const message =
          error?.payload?.error || error?.message || "Credenciales invalidas.";
        this.showLoginError(message);
      } finally {
        const submitBtn = this.dom.loginForm?.querySelector(
          'button[type="submit"]',
        );
        this.setButtonBusy(submitBtn, false);
      }
    },

    async logout() {
      try {
        await this.fetchJson("/api/logout", { method: "POST" });
      } catch (error) {
        console.warn("Fallo al cerrar sesion", error);
      }
      this.state.user = null;
      this.stopSessionMonitor();
      this.state.saleItems = [];
      this.showLogin();
    },

    async checkExistingSession() {
      try {
        const data = await this.fetchJson("/api/current_user");
        if (data?.user) {
          this.onAuthenticated(data.user);
        } else {
          this.showLogin();
        }
      } catch (error) {
        console.error("Error al validar sesion", error);
        this.showLogin("No se pudo verificar la sesion. Intenta nuevamente.");
      }
    },

    onAuthenticated(user) {
      this.state.user = {
        ...(user || {}),
        permissions: this.normalizePermissions(
          user?.permissions || {},
          user?.role || "",
        ),
        iva_percent: Number.isFinite(Number(user?.iva_percent))
          ? Number(user.iva_percent)
          : 19,
        allowed_payment_methods:
          Array.isArray(user?.allowed_payment_methods) &&
          user.allowed_payment_methods.length
            ? user.allowed_payment_methods
            : ["efectivo", "nequi", "daviplata", "transferencia"],
      };
      this.clearLoginError();
      if (this.dom.loginPage) {
        this.dom.loginPage.classList.add("d-none");
        this.dom.loginPage.setAttribute("hidden", "hidden");
      }
      if (this.dom.appShell) {
        this.dom.appShell.classList.remove("d-none");
        this.dom.appShell.removeAttribute("hidden");
      }
      this.setSidebarMenuOpen(false);
      this.state.saleItems = [];
      this.renderPaymentMethodOptions?.();
      this.renderSaleItems?.();
      if (this.dom.productIvaHint) {
        this.dom.productIvaHint.textContent = `IVA vigente: ${this.formatNumber(this.getCurrentIvaRate())}%`;
      }
      this.resetAiChatHistory();
      this.updateUserHeader();
      this.updatePermissionVisibility();
      this.renderAccountInfo?.();
      this.loadRoles?.({ silent: true });
      const landingPage = this.getDefaultPage();
      if (landingPage) {
        this.setActivePage(landingPage);
      }
      if (this.can("dashboard_view")) {
        this.loadDashboard?.();
      }
      if (this.can("products_view")) {
        this.loadProducts?.("");
        this.loadIvaConfig?.({ silent: true });
      }
      if (this.can("users_manage")) {
        this.loadUsers?.();
      }
      if (this.can("reports_view")) {
        this.generateReport?.({ silent: true });
      }
      if (this.can("statistics_view")) {
        this.generateStats?.({ silent: true });
      }
      if (this.can("audit_view")) {
        this.loadAuditTrail?.();
      }
      this.startSessionMonitor();
    },

    updateUserHeader() {
      if (!this.state.user) {
        return;
      }
      this.renderTopbarDateLabel();
      if (this.dom.userName) {
        this.dom.userName.textContent =
          this.state.user.name || this.state.user.username;
      }
      if (this.dom.userRoleLabel) {
        const roleLabel =
          this.state.user.role_name || this.state.user.role || "usuario";
        this.dom.userRoleLabel.textContent = String(roleLabel).toUpperCase();
      }
      if (this.dom.topbarGreetingName) {
        const roleOrName = (
          this.state.user.role_name ||
          this.state.user.name ||
          this.state.user.username ||
          "Usuario"
        ).trim();
        this.dom.topbarGreetingName.textContent = roleOrName;
      }
    },

    permissionForPage(page) {
      const permissionsByPage = {
        dashboard: "dashboard_view",
        sales: "sales_view",
        products: "products_view",
        reports: "reports_view",
        statistics: "statistics_view",
        users: "users_manage",
        audit: "audit_view",
        backups: "backups_manage",
      };
      return permissionsByPage[page] || null;
    },

    isPageAllowed(page) {
      if (!page || page === "account") {
        return true;
      }
      const requiredPermission = this.permissionForPage(page);
      if (!requiredPermission) {
        return true;
      }
      return this.can(requiredPermission);
    },

    getDefaultPage() {
      const pageOrder = [
        "dashboard",
        "sales",
        "products",
        "reports",
        "statistics",
        "users",
        "audit",
        "backups",
        "account",
      ];
      return (
        pageOrder.find((candidate) => this.isPageAllowed(candidate)) ||
        "account"
      );
    },

    updatePermissionVisibility() {
      const isAdmin = (this.state.user?.role || "").toLowerCase() === "admin";
      document.body.classList.toggle("user-admin", isAdmin);
      this.dom.permissionGated?.forEach((el) => {
        const permission = (el.dataset.permission || "").trim();
        const allowed = !permission || this.can(permission);
        el.classList.toggle("d-none", !allowed);
        if (allowed) {
          el.removeAttribute("hidden");
        } else {
          el.setAttribute("hidden", "hidden");
        }
      });
      this.dom.navLinks?.forEach((link) => {
        const page = link.dataset.page || "";
        if (!page) {
          return;
        }
        const allowed = this.isPageAllowed(page);
        link.classList.toggle("d-none", !allowed);
        if (allowed) {
          link.removeAttribute("hidden");
        } else {
          link.setAttribute("hidden", "hidden");
          link.removeAttribute("aria-current");
        }
      });
      if (this.state.activePage && !this.isPageAllowed(this.state.activePage)) {
        const fallbackPage = this.getDefaultPage();
        if (fallbackPage) {
          this.setActivePage(fallbackPage);
        }
      }
    },

    isCompactViewport() {
      return window.matchMedia("(max-width: 992px)").matches;
    },

    setSidebarMenuOpen(open) {
      const shouldOpen = Boolean(open) && this.isCompactViewport();
      this.state.sidebarOpen = shouldOpen;
      this.dom.appShell?.classList.toggle("sidebar-open", shouldOpen);
      document.body.classList.toggle("mobile-menu-open", shouldOpen);
      if (this.dom.menuToggleBtn) {
        this.dom.menuToggleBtn.setAttribute(
          "aria-expanded",
          shouldOpen ? "true" : "false",
        );
      }
    },

    toggleSidebarMenu() {
      this.setSidebarMenuOpen(!this.state.sidebarOpen);
    },

    closeSidebarMenu() {
      if (!this.state.sidebarOpen) {
        return;
      }
      this.setSidebarMenuOpen(false);
    },

    syncSidebarForViewport() {
      if (!this.isCompactViewport()) {
        this.setSidebarMenuOpen(false);
      }
    },

    setActivePage(page) {
      if (!this.isPageAllowed(page)) {
        const fallbackPage = this.getDefaultPage();
        if (fallbackPage && fallbackPage !== page) {
          this.setActivePage(fallbackPage);
        }
        return;
      }
      const pageId = `${page}Page`;
      const section = document.getElementById(pageId);
      if (!section) {
        return;
      }
      document
        .querySelectorAll(".page-content")
        .forEach((el) => el.classList.remove("active"));
      section.classList.add("active");
      this.state.activePage = page;
      if (this.dom.navLinks) {
        this.dom.navLinks.forEach((link) => {
          const isActive = link.dataset.page === page;
          link.classList.toggle("active", isActive);
          if (isActive) {
            link.setAttribute("aria-current", "page");
          } else {
            link.removeAttribute("aria-current");
          }
        });
      }
      if (
        this.dom.mainContent &&
        !this.dom.appShell?.classList.contains("d-none")
      ) {
        this.dom.mainContent.focus();
      }
      this.closeSidebarMenu();
      this.onPageActivated(page);
    },

    onPageActivated(page) {
      switch (page) {
        case "dashboard":
          if (this.can("dashboard_view")) {
            this.loadDashboard?.();
          }
          break;
        case "sales":
          if (this.can("sales_view")) {
            this.loadIvaConfig?.({ silent: true });
            this.queueSearch?.(this.dom.productSearch?.value.trim() || "");
            this.loadRecentSales?.({ silent: true });
          }
          break;
        case "products":
          if (this.can("products_view")) {
            this.loadIvaConfig?.({ silent: true });
            this.loadProducts?.(this.dom.productFilter?.value.trim() || "");
          }
          break;
        case "reports":
          if (this.can("reports_view") && !this.state.reportData) {
            this.generateReport?.();
          }
          break;
        case "statistics":
          if (this.can("statistics_view")) {
            this.generateStats?.();
          }
          break;
        case "users":
          if (this.can("users_manage")) {
            this.loadUsers?.();
          }
          break;
        case "audit":
          if (this.can("audit_view")) {
            this.loadAuditTrail?.();
          }
          break;
        case "backups":
          if (this.can("backups_manage")) {
            this.loadSystemStatus?.();
            this.loadBackupsList?.();
          }
          break;
        case "account":
          this.renderAccountInfo?.();
          break;
        default:
          break;
      }
    },
  });

  Object.assign(App, {
    async loadSessionStatus() {
      try {
        const data = await this.fetchJson("/api/session/status");
        this.state.sessionStatus = data;
        if (this.state.user && data) {
          this.state.user = {
            ...this.state.user,
            login_at: data.login_at || this.state.user.login_at,
            last_activity: data.last_activity || this.state.user.last_activity,
            session_expires_at:
              data.expires_at ?? this.state.user.session_expires_at,
            session_expires_at_utc:
              data.expires_at_utc ?? this.state.user.session_expires_at_utc,
          };
        }
        if (data.active) {
          if (
            !this.state.sessionWarningHidden &&
            data.seconds_left <= (data.warning_seconds || 300)
          ) {
            this.showSessionWarning(data.seconds_left);
          } else if (this.dom.sessionWarningBanner) {
            this.dom.sessionWarningBanner.classList.add("d-none");
          }
        }
      } catch (error) {
        if (error.status === 401) {
          window.alert("La sesion expiro.");
          this.logout();
        }
      }
      this.loadSystemStatus?.();
      this.renderAccountInfo?.();
    },

    renderOfflineStatus(status) {
      if (!this.dom.offlineBanner || !this.dom.offlineBannerText) {
        return;
      }
      const offline = Boolean(status?.offline);
      if (!offline) {
        this.dom.offlineBanner.classList.add("d-none");
        this.state.offlineDismissed = false;
        return;
      }
      if (this.state.offlineDismissed) {
        return;
      }
      const messageParts = ["Usando respaldo local."];
      if (status?.last_loaded) {
        messageParts.push(
          `Ultimo respaldo: ${this.formatDateTime(status.last_loaded)}.`,
        );
      }
      if (status?.last_error) {
        messageParts.push(String(status.last_error));
      }
      this.dom.offlineBannerText.textContent = messageParts.join(" ");
      this.dom.offlineBanner.classList.remove("d-none");
    },

    async loadSystemStatus() {
      if (!this.state.user) {
        return;
      }
      try {
        const data = await this.fetchJson("/api/system/status");
        this.state.systemStatus = data;
        if (!data.offline) {
          this.state.offlineDismissed = false;
        }
        this.renderOfflineStatus(data);
      } catch (error) {
        if (error.status === 401) {
          this.renderOfflineStatus(null);
          return;
        }
        const message =
          error?.payload?.error || error?.message || "Sin conexion";
        const fallback = { offline: true, last_error: message };
        this.renderOfflineStatus(fallback);
      }
    },

    setPlainStatus(element, message, isError = false) {
      if (!element) {
        return;
      }
      element.textContent = message || "";
      element.classList.toggle("text-danger", Boolean(isError));
    },

    async loadBackupsList() {
      if (!this.can("backups_manage") || !this.dom.backupsTable) {
        return;
      }
      this.showTableSkeleton(this.dom.backupsTable, 3);
      try {
        const payload = await this.fetchJson("/api/backups?limit=40");
        this.state.backups = Array.isArray(payload?.items) ? payload.items : [];
        this.renderBackupsTable(this.state.backups);
      } catch (error) {
        this.clearTableSkeleton(this.dom.backupsTable);
        const message =
          error?.payload?.error ||
          error?.message ||
          "No se pudo cargar el historial de respaldos.";
        this.dom.backupsTable.innerHTML = `<tr><td colspan="4" class="text-center text-muted">${this.escape(message)}</td></tr>`;
        this.applyTableLabels(this.dom.backupsTable);
      }
    },

    renderBackupsTable(items) {
      if (!this.dom.backupsTable) {
        return;
      }
      this.clearTableSkeleton(this.dom.backupsTable);
      if (!items?.length) {
        this.dom.backupsTable.innerHTML =
          '<tr><td colspan="4" class="text-center text-muted">No hay respaldos disponibles.</td></tr>';
        this.applyTableLabels(this.dom.backupsTable);
        return;
      }
      this.dom.backupsTable.innerHTML = items
        .map((item) => {
          const meta = item?.metadata || {};
          const pdfLink = item?.pdf_url
            ? `<a class="btn btn-sm btn-outline-secondary" href="${this.escape(item.pdf_url)}" target="_blank" rel="noopener">PDF</a>`
            : "";
          const jsonLink = item?.json_url
            ? `<a class="btn btn-sm btn-outline-secondary" href="${this.escape(item.json_url)}" target="_blank" rel="noopener">JSON</a>`
            : "";
          const restoreBtn = item?.json_filename
            ? `<button class="btn btn-sm btn-outline-danger" data-action="restore" data-filename="${this.escape(item.json_filename)}">Restaurar</button>`
            : "";
          return `
          <tr>
            <td>
              <div class="fw-semibold">${this.escape(item.json_filename || "-")}</div>
              <div class="text-muted small">${item.latest ? "Más reciente" : this.escape(item.reason || "manual")}</div>
            </td>
            <td>${this.formatDateTime(item.created_at)}</td>
            <td>
              <div class="small">${this.formatNumber(meta.productos || 0)} productos</div>
              <div class="small text-muted">${this.formatNumber(meta.ventas || 0)} ventas | ${this.formatNumber(meta.inventario_movimientos || 0)} movs</div>
            </td>
            <td class="text-end">
              <div class="d-flex gap-2 justify-content-end flex-wrap">
                ${jsonLink}
                ${pdfLink}
                ${restoreBtn}
              </div>
            </td>
          </tr>
        `;
        })
        .join("");
      this.applyTableLabels(this.dom.backupsTable);
    },

    async generateManualBackup() {
      if (!this.dom.generateBackupBtn) {
        return;
      }
      try {
        this.setButtonBusy(this.dom.generateBackupBtn, true);
        const payload = await this.fetchJson("/api/backups/manual", {
          method: "POST",
        });
        const created = payload?.created_at
          ? this.formatDateTime(payload.created_at)
          : "Respaldo generado";
        const parts = [];
        if (payload?.pdf_filename) {
          parts.push(`PDF: ${payload.pdf_filename}`);
        }
        if (payload?.json_filename) {
          parts.push(`JSON: ${payload.json_filename}`);
        }
        const pathInfo = parts.length ? ` (${parts.join(" | ")})` : "";
        this.setPlainStatus(this.dom.backupMessage, `${created}${pathInfo}`);
        const downloadUrl = payload?.pdf_url || payload?.json_url;
        if (downloadUrl) {
          const link = document.createElement("a");
          link.href = downloadUrl;
          link.target = "_blank";
          link.rel = "noopener";
          document.body.appendChild(link);
          link.click();
          link.remove();
        }
        this.state.offlineDismissed = false;
        this.loadSystemStatus?.();
        this.loadBackupsList?.();
      } catch (error) {
        const message =
          error?.payload?.error ||
          error?.message ||
          "No se pudo generar el respaldo.";
        this.setPlainStatus(this.dom.backupMessage, message, true);
      } finally {
        this.setButtonBusy(this.dom.generateBackupBtn, false);
      }
    },

    async restoreBackup(filename) {
      if (!filename || !this.can("backups_manage")) {
        return;
      }
      const accepted = window.confirm(
        `Se restaurará el snapshot ${filename}. Esta acción reemplaza productos, ventas e inventario actuales. ¿Deseas continuar?`,
      );
      if (!accepted) {
        return;
      }
      try {
        this.setPlainStatus(
          this.dom.backupMessage,
          `Restaurando ${filename}...`,
        );
        await this.fetchJson("/api/backups/restore", {
          method: "POST",
          body: { filename },
        });
        await this.refreshDataAfterRestore();
        this.setPlainStatus(
          this.dom.backupMessage,
          `Respaldo restaurado: ${filename}`,
        );
      } catch (error) {
        const message =
          error?.payload?.error ||
          error?.message ||
          "No se pudo restaurar el respaldo.";
        this.setPlainStatus(this.dom.backupMessage, message, true);
      }
    },

    async refreshDataAfterRestore() {
      this.state.reportData = null;
      this.state.forecastData = null;
      this.state.currentSaleDetail = null;
      this.closeModal?.("saleDetail");
      const tasks = [];
      tasks.push(this.loadBackupsList?.());
      tasks.push(this.loadSystemStatus?.());
      if (this.can("dashboard_view")) {
        tasks.push(this.loadDashboard?.({ silent: true }));
      }
      if (this.can("products_view")) {
        tasks.push(this.loadProducts?.(this.dom.productFilter?.value.trim() || ""));
        this.queueSearch?.(this.dom.productSearch?.value.trim() || "");
      }
      if (this.can("sales_view")) {
        tasks.push(this.loadRecentSales?.({ silent: true }));
      }
      if (this.can("reports_view")) {
        tasks.push(this.generateReport?.({ silent: true }));
      }
      if (this.can("statistics_view")) {
        tasks.push(this.generateStats?.({ silent: true }));
      }
      if (this.can("audit_view")) {
        tasks.push(this.loadAuditTrail?.());
      }
      await Promise.allSettled(tasks.filter(Boolean));
    },

    showSessionWarning(secondsLeft) {
      if (!this.dom.sessionWarningBanner || !this.dom.sessionWarningText) {
        return;
      }
      this.dom.sessionWarningText.textContent = `Quedan ${this.secondsToHms(secondsLeft)} antes de expirar.`;
      this.dom.sessionWarningBanner.classList.remove("d-none");
      this.state.sessionWarningHidden = false;
    },

    async keepAliveSession() {
      try {
        await this.fetchJson("/api/session/ping", { method: "POST" });
        this.state.sessionWarningHidden = false;
        this.dom.sessionWarningBanner?.classList.add("d-none");
        this.loadSessionStatus();
      } catch (error) {
        console.error("No se pudo mantener la sesion", error);
        window.alert("La sesion no se pudo renovar.");
        this.logout();
      }
    },

    startSessionMonitor() {
      this.stopSessionMonitor();
      this.loadSessionStatus();
      this.state.sessionPoll = window.setInterval(
        () => this.loadSessionStatus(),
        60 * 1000,
      );
    },

    stopSessionMonitor() {
      if (this.state.sessionPoll) {
        clearInterval(this.state.sessionPoll);
        this.state.sessionPoll = null;
      }
    },
  });

  Object.assign(App, {
    async loadDashboard(options = {}) {
      if (!this.can("dashboard_view")) {
        return;
      }
      const busyButton = options?.button || null;
      try {
        if (busyButton) {
          this.setButtonBusy(busyButton, true);
        }
        const fromCandidate = String(
          options?.from ?? this.dom.paymentDateFrom?.value ?? "",
        ).trim();
        const toCandidate = String(
          options?.to ?? this.dom.paymentDateTo?.value ?? "",
        ).trim();
        let url = "/api/dashboard";
        if (
          fromCandidate &&
          toCandidate &&
          new Date(fromCandidate) <= new Date(toCandidate)
        ) {
          const params = new URLSearchParams({
            from: fromCandidate,
            to: toCandidate,
          });
          url = `/api/dashboard?${params.toString()}`;
        }
        const data = await this.fetchJson(url);
        this.renderDashboard(data);
      } catch (error) {
        console.error("No se pudo cargar el dashboard", error);
      } finally {
        if (busyButton) {
          this.setButtonBusy(busyButton, false);
        }
      }
    },

    renderDashboard(data) {
      if (!data) {
        return;
      }
      if (this.dom.salesToday) {
        this.dom.salesToday.textContent = this.formatCurrency(
          data.ventas_hoy || 0,
        );
      }
      if (this.dom.lowStockTotal) {
        this.dom.lowStockTotal.textContent = this.formatNumber(
          data.stock_bajo || 0,
        );
      }
      if (this.dom.criticalStockTotal) {
        this.dom.criticalStockTotal.textContent = this.formatNumber(
          data.stock_critico || 0,
        );
      }
      if (this.dom.totalProducts) {
        this.dom.totalProducts.textContent = this.formatNumber(
          data.total_productos || 0,
        );
      }
      if (this.dom.missingImagesTotal) {
        this.dom.missingImagesTotal.textContent = this.formatNumber(
          data.productos_sin_imagen || 0,
        );
      }
      if (this.dom.popularProducts) {
        const items = data.productos_populares || [];
        if (!items.length) {
          this.dom.popularProducts.innerHTML =
            '<p class="text-muted small mb-0">Sin ventas recientes.</p>';
        } else {
          this.dom.popularProducts.innerHTML = items
            .map(
              (item) => `
            <div class="dashboard-item">
              <div>
                <div class="fw-semibold">${this.escape(item.nombre)}</div>
                <div class="text-muted small">Unidades: ${this.formatNumber(item.total_vendido || 0)}</div>
              </div>
            </div>
          `,
            )
            .join("");
        }
      }
      if (this.dom.lowStockAlerts) {
        const alerts = data.productos_stock_bajo || [];
        if (!alerts.length) {
          this.dom.lowStockAlerts.innerHTML =
            '<p class="text-muted small mb-0">Sin alertas activas.</p>';
        } else {
          this.dom.lowStockAlerts.innerHTML = alerts
            .map(
              (item) => `
            <div class="dashboard-item">
              <div>
                <div class="fw-semibold">${this.escape(item.nombre)}</div>
                <div class="text-muted small">Stock: ${this.formatNumber(item.stock || 0)} | Minimo: ${this.formatNumber(item.min_stock || 0)}</div>
              </div>
              <span class="badge ${item.alert_badge_class || "bg-warning"}">${this.escape(item.alert_message || "Stock bajo")}</span>
            </div>
          `,
            )
            .join("");
          }
      }
      this.renderPaymentBreakdown(
        data.payment_breakdown || [],
        data.payment_period || null,
      );
    },

    renderPaymentBreakdown(entries, period = null) {
      if (!this.dom.paymentMethodsSummary || !this.dom.paymentMethodsList) {
        return;
      }
      if (!entries.length) {
        if (period?.desde && period?.hasta) {
          this.dom.paymentMethodsSummary.textContent = [
            "0 metodos",
            `${this.formatDateOnly(period.desde)} a ${this.formatDateOnly(period.hasta)}`,
            `Total ${this.formatCurrency(0)}`,
          ].join(" | ");
        } else {
          this.dom.paymentMethodsSummary.textContent = "Sin datos";
        }
        this.dom.paymentMethodsList.innerHTML =
          period?.desde && period?.hasta
            ? '<p class="text-muted small mb-0">No hay ventas registradas en el rango seleccionado.</p>'
            : '<p class="text-muted small mb-0">Registra ventas para ver la distribucion.</p>';
        return;
      }
      const total = entries.reduce(
        (sum, item) => sum + Number(item.monto_total || 0),
        0,
      );
      const summaryParts = [`${entries.length} metodos`];
      if (period?.desde && period?.hasta) {
        summaryParts.push(
          `${this.formatDateOnly(period.desde)} a ${this.formatDateOnly(period.hasta)}`,
        );
      }
      summaryParts.push(`Total ${this.formatCurrency(total)}`);
      this.dom.paymentMethodsSummary.textContent = summaryParts.join(" | ");
      const colors = [
        "bg-primary",
        "bg-success",
        "bg-info",
        "bg-warning",
        "bg-secondary",
      ];
      this.dom.paymentMethodsList.innerHTML = entries
        .map((item, index) => {
          const amount = Number(item.monto_total || 0);
          const percentage = total > 0 ? Math.round((amount / total) * 100) : 0;
          return `
          <div class="mb-3">
            <div class="d-flex justify-content-between small">
              <span class="text-uppercase">${this.escape(item.metodo_pago || "")}</span>
              <span>${this.formatCurrency(amount)} (${percentage}%)</span>
            </div>
            <div class="progress" style="height: 6px;">
              <div class="progress-bar ${colors[index % colors.length]}" style="width: ${percentage}%"></div>
            </div>
            <div class="text-muted small mt-1">Ventas: ${this.formatNumber(item.total_ventas || 0)}</div>
          </div>
        `;
        })
        .join("");
    },

    queueSearch(term) {
      if (this.state.searchTimer) {
        clearTimeout(this.state.searchTimer);
      }
      this.state.searchTimer = window.setTimeout(
        () => this.searchProducts(term),
        250,
      );
    },

    async searchProducts(term) {
      try {
        const url = term
          ? `/api/productos?search=${encodeURIComponent(term)}`
          : "/api/productos";
        const results = await this.fetchJson(url);
        const rawResults = Array.isArray(results) ? results : [];
        const limitedResults = rawResults.slice(0, 5);
        this.state.searchResults = limitedResults;
        this.renderSearchResults(limitedResults, rawResults.length);
      } catch (error) {
        console.error("Fallo la busqueda de productos", error);
        if (this.dom.searchResults) {
          this.dom.searchResults.innerHTML =
            '<div class="alert alert-warning">No se pudo buscar productos.</div>';
        }
      }
    },

    renderSearchResults(
      results,
      totalCount = Array.isArray(results) ? results.length : 0,
    ) {
      if (!this.dom.searchResults) {
        return;
      }
      const canCreateSales = this.can("sales_create");
      if (!results?.length) {
        this.dom.searchResults.innerHTML =
          '<p class="text-muted small mb-0">Escribe para buscar productos.</p>';
        return;
      }
      const cards = results
        .map((product) => {
          const priceBase = this.getProductBasePrice(product);
          const ivaRate = this.getProductIvaRate(product);
          const ivaValue = this.getProductIvaValue(product);
          const finalPrice = this.getProductPriceWithIva(product);
          return `
        <div class="sale-result-card d-flex justify-content-between align-items-center" data-id="${product.id}">
          <div class="sale-result-main">
            <img src="${this.resolveProductImageUrl(product)}" class="product-thumb-sm" alt="${this.escape(product.nombre || "Producto")}">
            <div>
              <div class="fw-semibold">${this.escape(product.nombre)}</div>
              <div class="text-muted small">
                Base: ${this.formatCurrency(priceBase)} |
                IVA ${this.formatNumber(ivaRate)}%: ${this.formatCurrency(ivaValue)} |
                Final: ${this.formatCurrency(finalPrice)} |
                Stock: ${this.formatNumber(product.stock || 0)}
              </div>
            </div>
          </div>
          <button class="btn btn-sm btn-primary" data-action="add" data-id="${product.id}" ${canCreateSales ? "" : "disabled"}>${canCreateSales ? "Agregar" : "Sin permiso"}</button>
        </div>
      `;
        })
        .join("");
      const note =
        totalCount > results.length
          ? `<p class="text-muted small mb-0">Mostrando ${results.length} de ${totalCount} resultados. Refina la busqueda para ver otros productos.</p>`
          : "";
      this.dom.searchResults.innerHTML = `${cards}${note}`;
    },

    addSaleItem(product) {
      if (!product) {
        return;
      }
      const priceBase = this.getProductBasePrice(product);
      const stock = Number(product.stock ?? 0);
      const ivaRate = this.getProductIvaRate(product);
      const existing = this.state.saleItems.find(
        (item) => item.id === product.id,
      );
      if (existing) {
        if (!stock || existing.quantity < stock) {
          existing.quantity += 1;
        }
      } else {
        this.state.saleItems.push({
          id: product.id,
          nombre: product.nombre,
          price: priceBase,
          ivaRate: Number.isFinite(ivaRate)
            ? ivaRate
            : this.getCurrentIvaRate(),
          stock,
          image: this.resolveProductImageUrl(product),
          quantity: 1,
        });
      }
      this.renderSaleItems();
    },

    updateSaleItemQuantity(id, quantity) {
      const item = this.state.saleItems.find((saleItem) => saleItem.id === id);
      if (!item) {
        return;
      }
      const max =
        Number.isFinite(item.stock) && item.stock > 0 ? item.stock : quantity;
      item.quantity = Math.max(1, Math.min(quantity, max));
      this.renderSaleItems();
    },

    removeSaleItem(id) {
      this.state.saleItems = this.state.saleItems.filter(
        (item) => item.id !== id,
      );
      this.renderSaleItems();
    },

    resetSale(successMessage = "") {
      this.state.saleItems = [];
      this.renderSaleItems();
      if (this.dom.saleMessage) {
        if (successMessage) {
          this.setAlert(this.dom.saleMessage, successMessage, "success");
        } else {
          this.dom.saleMessage.classList.add("d-none");
        }
      }
    },

    renderSaleItems() {
      if (
        !this.dom.saleItems ||
        !this.dom.saleTotal ||
        !this.dom.completeSaleBtn
      ) {
        return;
      }
      const ivaRateDefault = this.getCurrentIvaRate();
      if (!this.state.saleItems.length) {
        this.dom.saleItems.innerHTML =
          '<p class="text-muted mb-0">Selecciona productos para la venta.</p>';
        if (this.dom.saleSubtotal) {
          this.dom.saleSubtotal.textContent = this.formatCurrency(0);
        }
        if (this.dom.saleIva) {
          this.dom.saleIva.textContent = this.formatCurrency(0);
        }
        this.dom.saleTotal.textContent = this.formatCurrency(0);
        this.dom.completeSaleBtn.disabled = true;
        if (this.dom.saleIvaRate) {
          this.dom.saleIvaRate.textContent = "Variable";
        }
        return;
      }
      let subtotal = 0;
      let ivaTotal = 0;
      const ivaSet = new Set();
      this.dom.saleItems.innerHTML = this.state.saleItems
        .map((item) => {
          const unitBase = Number(item.price || 0);
          const ivaRate = Number.isFinite(Number(item.ivaRate))
            ? Number(item.ivaRate)
            : ivaRateDefault;
          ivaSet.add(this.roundMoney(ivaRate));
          const unitIva = this.roundMoney((unitBase * ivaRate) / 100);
          const unitFinal = this.roundMoney(unitBase + unitIva);
          const lineBase = this.roundMoney(unitBase * item.quantity);
          const lineIva = this.roundMoney(unitIva * item.quantity);
          const lineTotal = this.roundMoney(unitFinal * item.quantity);
          subtotal += lineBase;
          ivaTotal += lineIva;
          return `
          <div class="sale-item-card border rounded p-2 mb-2" data-id="${item.id}">
            <div class="d-flex justify-content-between align-items-center gap-3 flex-wrap">
              <div class="sale-result-main">
                <img src="${this.resolveProductImageUrl({ nombre: item.nombre, imagen_url: item.image })}" class="product-thumb-sm" alt="${this.escape(item.nombre || "Producto")}">
                <div>
                  <div class="fw-semibold">${this.escape(item.nombre)}</div>
                  <div class="text-muted small">
                    Base: ${this.formatCurrency(unitBase)} |
                    IVA ${this.formatNumber(ivaRate)}%: ${this.formatCurrency(unitIva)} |
                    Final: ${this.formatCurrency(unitFinal)} |
                    Stock: ${this.formatNumber(item.stock || 0)}
                  </div>
                </div>
              </div>
              <div class="d-flex align-items-center gap-2 flex-wrap">
                <input type="number" min="1" ${item.stock ? `max="${item.stock}"` : ""} value="${item.quantity}" data-action="quantity" data-id="${item.id}" class="form-control form-control-sm" style="width: 80px;">
                <div class="fw-semibold item-total">${this.formatCurrency(lineTotal)}</div>
                <button class="btn btn-outline-danger btn-sm" data-action="remove" data-id="${item.id}"><i class="bi bi-trash"></i></button>
              </div>
            </div>
          </div>
        `;
        })
        .join("");
      subtotal = this.roundMoney(subtotal);
      ivaTotal = this.roundMoney(ivaTotal);
      const total = this.roundMoney(subtotal + ivaTotal);
      if (this.dom.saleSubtotal) {
        this.dom.saleSubtotal.textContent = this.formatCurrency(subtotal);
      }
      if (this.dom.saleIva) {
        this.dom.saleIva.textContent = this.formatCurrency(ivaTotal);
      }
      if (this.dom.saleIvaRate) {
        this.dom.saleIvaRate.textContent =
          ivaSet.size === 1
            ? `${this.formatNumber(Array.from(ivaSet)[0])}%`
            : "Variable";
      }
      this.dom.saleTotal.textContent = this.formatCurrency(total);
      this.dom.completeSaleBtn.disabled = total <= 0;
    },

    async completeSale() {
      if (!this.can("sales_create")) {
        return;
      }
      if (!this.state.saleItems.length) {
        return;
      }
      const paymentMethod = this.dom.paymentMethod?.value;
      if (!paymentMethod) {
        this.setAlert(
          this.dom.saleMessage,
          "Selecciona un metodo de pago.",
          "warning",
        );
        return;
      }
      try {
        this.setAlert(this.dom.saleMessage, "Registrando venta...", "info");
        this.dom.completeSaleBtn.disabled = true;
        const payload = {
          payment_method: paymentMethod,
          items: this.state.saleItems.map((item) => ({
            id: item.id,
            quantity: item.quantity,
            price: item.price,
          })),
        };
        const response = await this.fetchJson("/api/ventas", {
          method: "POST",
          body: payload,
        });
        if (response?.success) {
          const totals = response?.totals || {};
          const ivaRate = Number.isFinite(Number(totals.iva_percent))
            ? Number(totals.iva_percent)
            : this.getCurrentIvaRate();
          const ivaMode =
            totals.iva_mode === "por_producto"
              ? `IVA por producto: ${this.formatCurrency(totals.iva || 0)}`
              : `IVA ${this.formatNumber(ivaRate)}%: ${this.formatCurrency(totals.iva || 0)}`;
          const successMessage = `Venta registrada por ${this.formatCurrency(totals.total || response.total || 0)} (${ivaMode}).`;
          this.resetSale(successMessage);
          this.loadDashboard();
          this.loadRecentSales?.({ silent: true });
          this.loadProducts?.(this.dom.productFilter?.value.trim() || "");
          this.queueSearch?.(this.dom.productSearch?.value.trim() || "");
          if (response.recommendations) {
            this.renderPostSaleRecommendations(response.recommendations);
          }
        } else {
          this.setAlert(
            this.dom.saleMessage,
            "La venta no pudo registrarse.",
            "danger",
          );
        }
      } catch (error) {
        const message =
          error?.payload?.message ||
          error?.message ||
          "No se pudo registrar la venta.";
        this.setAlert(this.dom.saleMessage, message, "danger");
      } finally {
        this.dom.completeSaleBtn.disabled = false;
      }
    },

    describeComboSuggestion(entry) {
      if (entry == null) {
        return "";
      }
      if (typeof entry === "string") {
        return entry;
      }
      if (Array.isArray(entry)) {
        return entry.join(" + ");
      }
      if (typeof entry !== "object") {
        return String(entry);
      }
      const items =
        Array.isArray(entry.items) && entry.items.length
          ? entry.items
          : Array.isArray(entry.products) && entry.products.length
            ? entry.products
            : null;
      const headline =
        entry.title ||
        entry.nombre ||
        entry.name ||
        (items ? items.join(" + ") : "");
      const details = [];
      const count = Number(entry.count ?? entry.ventas);
      if (Number.isFinite(count) && count > 0) {
        details.push(`${this.formatNumber(count)} ventas`);
      }
      const support = Number(entry.support_pct ?? entry.support);
      if (Number.isFinite(support) && support > 0) {
        const supportText = support.toFixed(1).replace(/\.0$/, "");
        details.push(`${supportText}% de órdenes`);
      }
      const ticket = Number(
        entry.avg_ticket ??
          entry.ticket ??
          entry.precio_promedio ??
          entry.total,
      );
      if (Number.isFinite(ticket) && ticket > 0) {
        details.push(`ticket ${this.formatCurrency(ticket)}`);
      }
      return (
        [headline, details.join(" | ")].filter(Boolean).join(" — ") ||
        JSON.stringify(entry)
      );
    },

    describeRestockAlert(entry) {
      if (entry == null) {
        return "";
      }
      if (typeof entry === "string") {
        return entry;
      }
      if (Array.isArray(entry)) {
        return entry.join(", ");
      }
      if (typeof entry !== "object") {
        return String(entry);
      }
      const name =
        entry.product || entry.nombre || entry.name || entry.item || "";
      const pieces = [];
      const stock = Number(entry.stock ?? entry.stock_actual);
      if (Number.isFinite(stock)) {
        pieces.push(`stock ${this.formatNumber(stock)}`);
      }
      const minStock = Number(entry.min_stock ?? entry.minimo ?? entry.min);
      if (Number.isFinite(minStock)) {
        pieces.push(`mín ${this.formatNumber(minStock)}`);
      }
      const recommended = Number(
        entry.recommended ?? entry.sugerido ?? entry.reponer ?? entry.cantidad,
      );
      if (Number.isFinite(recommended) && recommended > 0) {
        pieces.push(`reponer ${this.formatNumber(recommended)}`);
      }
      const weekly = Number(
        entry.weekly_qty ?? entry.ventas_semana ?? entry.ventas_7d,
      );
      if (Number.isFinite(weekly) && weekly > 0) {
        pieces.push(`7d: ${this.formatNumber(weekly)} uds`);
      }
      const target = Number(entry.target_stock ?? entry.objetivo);
      if (Number.isFinite(target) && target > 0) {
        pieces.push(`objetivo ${this.formatNumber(target)}`);
      }
      return (
        [name, pieces.join(" | ")].filter(Boolean).join(": ") ||
        JSON.stringify(entry)
      );
    },

    renderPostSaleRecommendations(data) {
      if (
        !this.dom.postSaleRecommendations ||
        !this.dom.postSaleRecommendationsContent
      ) {
        return;
      }
      const combos = Array.isArray(data?.combo_suggestions)
        ? data.combo_suggestions
        : [];
      const restock = Array.isArray(data?.restock_alerts)
        ? data.restock_alerts
        : [];
      const fragments = [];
      const comboLines = combos
        .map((item) => this.describeComboSuggestion(item))
        .filter(Boolean);
      if (comboLines.length) {
        fragments.push(
          `<div class="mb-2"><strong>Combos sugeridos:</strong><br>${comboLines.map((line) => this.escape(line)).join("<br>")}</div>`,
        );
      }
      const restockLines = restock
        .map((item) => this.describeRestockAlert(item))
        .filter(Boolean);
      if (restockLines.length) {
        fragments.push(
          `<div><strong>Reposicion recomendada:</strong><br>${restockLines.map((line) => this.escape(line)).join("<br>")}</div>`,
        );
      }
      if (!fragments.length) {
        this.dom.postSaleRecommendations.classList.add("d-none");
        return;
      }
      this.dom.postSaleRecommendationsContent.innerHTML = fragments.join("");
      this.dom.postSaleRecommendations.classList.remove("d-none");
    },
  });

  Object.assign(App, {
    async loadIvaConfig(options = {}) {
      if (!this.can("products_view")) {
        return;
      }
      const silent = Boolean(options?.silent);
      try {
        const data = await this.fetchJson("/api/config/iva");
        const ivaPercent = Number(data?.iva_percent);
        if (Number.isFinite(ivaPercent)) {
          this.state.user = {
            ...(this.state.user || {}),
            iva_percent: ivaPercent,
          };
        }
        if (
          Array.isArray(data?.allowed_payment_methods) &&
          data.allowed_payment_methods.length
        ) {
          this.state.user = {
            ...(this.state.user || {}),
            allowed_payment_methods: data.allowed_payment_methods,
          };
        }
        if (this.dom.ivaPercentInput && Number.isFinite(ivaPercent)) {
          this.dom.ivaPercentInput.value = String(this.roundMoney(ivaPercent));
        }
        if (this.dom.ivaConfigMessage && !silent) {
          this.dom.ivaConfigMessage.textContent = `IVA vigente: ${this.formatNumber(this.getCurrentIvaRate())}%`;
          this.dom.ivaConfigMessage.classList.remove("text-danger");
        }
        if (this.dom.productIvaHint) {
          this.dom.productIvaHint.textContent = `IVA vigente: ${this.formatNumber(this.getCurrentIvaRate())}%`;
        }
        this.renderPaymentMethodOptions?.();
        this.renderSaleItems?.();
      } catch (error) {
        if (!silent && this.dom.ivaConfigMessage) {
          const message =
            error?.payload?.error ||
            error?.message ||
            "No se pudo leer el IVA actual.";
          this.dom.ivaConfigMessage.textContent = message;
          this.dom.ivaConfigMessage.classList.add("text-danger");
        }
      }
    },

    async saveIvaConfig() {
      if (!this.can("products_manage")) {
        return;
      }
      const value = Number(this.dom.ivaPercentInput?.value);
      if (!Number.isFinite(value) || value < 0 || value > 100) {
        if (this.dom.ivaConfigMessage) {
          this.dom.ivaConfigMessage.textContent =
            "Ingresa un IVA valido entre 0 y 100.";
          this.dom.ivaConfigMessage.classList.add("text-danger");
        }
        return;
      }
      try {
        this.setButtonBusy(this.dom.saveIvaBtn, true);
        const response = await this.fetchJson("/api/config/iva", {
          method: "PUT",
          body: { iva_percent: value },
        });
        const ivaPercent = Number(response?.iva_percent);
        if (Number.isFinite(ivaPercent)) {
          this.state.user = {
            ...(this.state.user || {}),
            iva_percent: ivaPercent,
          };
        }
        if (
          Array.isArray(response?.allowed_payment_methods) &&
          response.allowed_payment_methods.length
        ) {
          this.state.user = {
            ...(this.state.user || {}),
            allowed_payment_methods: response.allowed_payment_methods,
          };
        }
        this.renderPaymentMethodOptions?.();
        this.renderSaleItems?.();
        this.loadProducts?.(this.dom.productFilter?.value.trim() || "");
        this.queueSearch?.(this.dom.productSearch?.value.trim() || "");
        if (this.dom.ivaConfigMessage) {
          this.dom.ivaConfigMessage.textContent = `IVA actualizado a ${this.formatNumber(this.getCurrentIvaRate())}%`;
          this.dom.ivaConfigMessage.classList.remove("text-danger");
        }
        if (this.dom.productIvaHint) {
          this.dom.productIvaHint.textContent = `IVA vigente: ${this.formatNumber(this.getCurrentIvaRate())}%`;
        }
      } catch (error) {
        if (this.dom.ivaConfigMessage) {
          const message =
            error?.payload?.error ||
            error?.message ||
            "No se pudo actualizar el IVA.";
          this.dom.ivaConfigMessage.textContent = message;
          this.dom.ivaConfigMessage.classList.add("text-danger");
        }
      } finally {
        this.setButtonBusy(this.dom.saveIvaBtn, false);
      }
    },

    async exportProducts(format = "csv") {
      if (!this.can("products_view")) {
        return;
      }
      const button =
        format === "excel"
          ? this.dom.exportProductsExcelBtn
          : this.dom.exportProductsPdfBtn;
      try {
        this.setButtonBusy(button, true);
        const extension = format === "excel" ? "xlsx" : format === "pdf" ? "pdf" : "csv";
        await this.downloadApiFile(
          `/api/productos/export?format=${encodeURIComponent(format)}`,
          `inventario-productos.${extension}`,
        );
        this.setPlainStatus(
          this.dom.productImportMessage,
          `Inventario exportado en formato ${format === "excel" ? "Excel" : format === "pdf" ? "PDF" : "CSV"}.`,
        );
      } catch (error) {
        const message =
          error?.payload?.error ||
          error?.message ||
          "No se pudo exportar el inventario.";
        this.setPlainStatus(this.dom.productImportMessage, message, true);
      } finally {
        this.setButtonBusy(button, false);
      }
    },

    async importProducts(file) {
      if (!file || !this.can("products_manage")) {
        return;
      }
      const form = new FormData();
      form.append("file", file);
      try {
        this.setButtonBusy(this.dom.importProductsBtn, true);
        this.setPlainStatus(
          this.dom.productImportMessage,
          `Importando ${file.name}...`,
        );
        const payload = await this.fetchJson("/api/productos/import", {
          method: "POST",
          body: form,
        });
        this.setPlainStatus(
          this.dom.productImportMessage,
          `Importación completada. Nuevos: ${this.formatNumber(payload.created || 0)} | Actualizados: ${this.formatNumber(payload.updated || 0)}.`,
        );
        if (this.dom.productImportInput) {
          this.dom.productImportInput.value = "";
        }
        this.loadProducts?.(this.dom.productFilter?.value.trim() || "");
        this.queueSearch?.(this.dom.productSearch?.value.trim() || "");
        this.loadDashboard?.();
      } catch (error) {
        const message =
          error?.payload?.error ||
          error?.message ||
          "No se pudo importar el inventario.";
        this.setPlainStatus(this.dom.productImportMessage, message, true);
      } finally {
        this.setButtonBusy(this.dom.importProductsBtn, false);
      }
    },

    async loadProducts(search) {
      if (!this.can("products_view")) {
        return;
      }
      if (this.dom.productsTable) {
        this.showTableSkeleton(this.dom.productsTable);
      }
      try {
        const params = new URLSearchParams();
        if (search) {
          params.set("search", search);
        }
        if (this.can("products_manage")) {
          params.set("include_inactive", "1");
        }
        const query = params.toString();
        const url = query ? `/api/productos?${query}` : "/api/productos";
        const products = await this.fetchJson(url);
        this.state.products = Array.isArray(products) ? products : [];
        this.renderProductsTable(this.state.products);
      } catch (error) {
        console.error("No se pudieron cargar los productos", error);
        if (this.dom.productsTable) {
          this.clearTableSkeleton(this.dom.productsTable);
          const message =
            error?.payload?.error ||
            error?.message ||
            "No se pudieron cargar los productos.";
          this.dom.productsTable.innerHTML = `<tr><td colspan="6" class="text-center text-muted">${this.escape(message)}</td></tr>`;
          this.applyTableLabels(this.dom.productsTable);
        }
      }
    },

    renderProductsTable(products) {
      if (!this.dom.productsTable) {
        return;
      }
      this.clearTableSkeleton(this.dom.productsTable);
      if (!products?.length) {
        this.dom.productsTable.innerHTML =
          '<tr><td colspan="6" class="text-center text-muted">No hay productos registrados.</td></tr>';
        this.applyTableLabels(this.dom.productsTable);
        return;
      }
      const canManage = this.can("products_manage");
      this.dom.productsTable.innerHTML = products
        .map((product) => {
          const priceBase = this.getProductBasePrice(product);
          const ivaRate = this.getProductIvaRate(product);
          const ivaValue = this.getProductIvaValue(product);
          const priceFinal = this.getProductPriceWithIva(product);
          const price = `
          <div>${this.formatCurrency(priceBase)}</div>
          <small class="text-muted">IVA ${this.formatNumber(ivaRate)}%: ${this.formatCurrency(ivaValue)}</small><br>
          <strong>${this.formatCurrency(priceFinal)}</strong>
        `;
          const stock = this.formatNumber(product.stock || 0);
          const minStock = this.formatNumber(product.min_stock || 0);
          const isActive = product.activo !== false && product.activo !== 0;
          const stateBadge = isActive
            ? '<span class="badge bg-success-subtle text-success-emphasis">Activo</span>'
            : '<span class="badge bg-secondary">Inactivo</span>';
          const badgeClass = product.alert_badge_class || "bg-secondary";
          const badgeLabel = product.alert_message || "Sin alertas";
          const actions = canManage
            ? `
            <button class="btn btn-sm btn-outline-primary me-1" data-action="edit">Editar</button>
            <button class="btn btn-sm btn-outline-secondary me-1" data-action="min">Minimo</button>
            <button class="btn btn-sm ${isActive ? "btn-outline-danger" : "btn-outline-success"} me-1" data-action="toggle-state" data-active="${isActive ? "1" : "0"}">${isActive ? "Desactivar" : "Activar"}</button>
          `
            : '<span class="text-muted small">Solo lectura</span>';
          return `
          <tr data-id="${product.id}">
            <td>
              <div class="product-cell-main">
                <img src="${this.resolveProductImageUrl(product)}" class="product-thumb" alt="${this.escape(product.nombre || "Producto")}">
                <div>
                  <div class="fw-semibold">${this.escape(product.nombre)}</div>
                  <div class="text-muted small">ID ${product.id}</div>
                </div>
              </div>
            </td>
            <td>${this.escape(product.categoria || "-")}</td>
            <td>${price}</td>
            <td>${stock}</td>
            <td>
              <span class="badge ${badgeClass}">${this.escape(badgeLabel)}</span><br>
              <small class="text-muted">Min: ${minStock}</small><br>
              <small>${stateBadge}</small>
            </td>
            <td class="text-end">${actions}</td>
          </tr>
        `;
        })
        .join("");
      this.applyTableLabels(this.dom.productsTable);
    },

    async loadAuditTrail() {
      if (!this.can("audit_view")) {
        return;
      }
      if (this.dom.auditTable) {
        this.showTableSkeleton(this.dom.auditTable);
      }
      if (this.dom.auditSummary) {
        this.dom.auditSummary.textContent = "Cargando auditoria...";
      }
      const params = new URLSearchParams({ limit: "400", include_system: "0" });
      const from = this.dom.auditDateFrom?.value || "";
      const to = this.dom.auditDateTo?.value || "";
      const action = (this.dom.auditActionFilter?.value || "").trim();
      const user = (this.dom.auditUserFilter?.value || "").trim();
      if (from) {
        params.set("from", from);
      }
      if (to) {
        params.set("to", to);
      }
      if (action) {
        params.set("action", action);
      }
      if (user) {
        params.set("user", user);
      }
      try {
        const data = await this.fetchJson(
          `/api/auditoria?${params.toString()}`,
        );
        this.renderAuditTrail(data.eventos || [], data.summary || null);
      } catch (error) {
        console.error("No se pudo cargar la auditoria", error);
        if (this.dom.auditTable) {
          this.clearTableSkeleton(this.dom.auditTable);
          this.dom.auditTable.innerHTML =
            '<tr><td colspan="6" class="text-center text-muted">No se pudo cargar la auditoria.</td></tr>';
          this.applyTableLabels(this.dom.auditTable);
        }
        if (this.dom.auditSummary) {
          this.dom.auditSummary.textContent =
            "No se pudieron obtener eventos de auditoria.";
        }
      } finally {
        this.clearTableSkeleton(this.dom.auditTable);
      }
    },

    async exportAuditReport(format = "pdf") {
      if (!this.can("audit_view")) {
        return;
      }
      const selectedFormat =
        String(format || "").toLowerCase() === "excel" ? "excel" : "pdf";
      const button =
        selectedFormat === "excel"
          ? this.dom.auditExportExcelBtn
          : this.dom.auditExportPdfBtn;
      const params = new URLSearchParams({
        include_system: "0",
        limit: "2000",
        format: selectedFormat,
      });
      const from = this.dom.auditDateFrom?.value || "";
      const to = this.dom.auditDateTo?.value || "";
      const action = (this.dom.auditActionFilter?.value || "").trim();
      const user = (this.dom.auditUserFilter?.value || "").trim();
      if (from) {
        params.set("from", from);
      }
      if (to) {
        params.set("to", to);
      }
      if (action) {
        params.set("action", action);
      }
      if (user) {
        params.set("user", user);
      }
      try {
        this.setButtonBusy(button, true);
        await this.downloadApiFile(
          `/api/auditoria/export?${params.toString()}`,
          `reporte-auditoria.${selectedFormat === "excel" ? "xlsx" : "pdf"}`,
        );
      } catch (error) {
        const message =
          error?.payload?.error ||
          error?.message ||
          "No se pudo exportar la auditoria.";
        window.alert(message);
      } finally {
        this.setButtonBusy(button, false);
      }
    },

    formatAuditDetails(entry) {
      const eventType = String(entry?.event_type || "").toLowerCase();
      const details =
        entry && typeof entry.details === "object" ? entry.details : {};
      if (eventType === "producto_actualizado") {
        const parts = [];
        const getBeforeAfter = (fieldName) => {
          const field = details?.[fieldName];
          if (!field || typeof field !== "object") {
            return null;
          }
          return { before: field.before, after: field.after };
        };
        const nameChange = getBeforeAfter("nombre");
        if (nameChange && nameChange.before !== nameChange.after) {
          parts.push(
            `Nombre: ${nameChange.before || "-"} -> ${nameChange.after || "-"}`,
          );
        }
        const categoryChange = getBeforeAfter("categoria");
        if (categoryChange && categoryChange.before !== categoryChange.after) {
          parts.push(
            `Categoria: ${categoryChange.before || "-"} -> ${categoryChange.after || "-"}`,
          );
        }
        const priceChange =
          details?.precio && typeof details.precio === "object"
            ? details.precio
            : null;
        if (priceChange) {
          const beforePrice = Number(priceChange.before);
          const afterPrice = Number(priceChange.after);
          if (
            Number.isFinite(beforePrice) &&
            Number.isFinite(afterPrice) &&
            beforePrice !== afterPrice
          ) {
            parts.push(
              `Precio: ${this.formatCurrency(beforePrice)} -> ${this.formatCurrency(afterPrice)}`,
            );
          }
        }
        const ivaChange = getBeforeAfter("iva_percent");
        if (ivaChange && Number(ivaChange.before) !== Number(ivaChange.after)) {
          const beforeIva = Number(ivaChange.before);
          const afterIva = Number(ivaChange.after);
          if (Number.isFinite(beforeIva) && Number.isFinite(afterIva)) {
            parts.push(
              `IVA: ${this.formatNumber(beforeIva)}% -> ${this.formatNumber(afterIva)}%`,
            );
          }
        }
        const stockChange = getBeforeAfter("stock");
        if (
          stockChange &&
          Number(stockChange.before) !== Number(stockChange.after)
        ) {
          const beforeStock = Number(stockChange.before);
          const afterStock = Number(stockChange.after);
          if (Number.isFinite(beforeStock) && Number.isFinite(afterStock)) {
            parts.push(
              `Stock: ${this.formatNumber(beforeStock)} -> ${this.formatNumber(afterStock)}`,
            );
          }
        }
        const minStockChange = getBeforeAfter("min_stock");
        if (
          minStockChange &&
          Number(minStockChange.before) !== Number(minStockChange.after)
        ) {
          const beforeMin = Number(minStockChange.before);
          const afterMin = Number(minStockChange.after);
          if (Number.isFinite(beforeMin) && Number.isFinite(afterMin)) {
            parts.push(
              `Minimo: ${this.formatNumber(beforeMin)} -> ${this.formatNumber(afterMin)}`,
            );
          }
        }
        const imageChange =
          details?.imagen && typeof details.imagen === "object"
            ? details.imagen
            : null;
        if (imageChange) {
          const action = String(imageChange.action || "").toLowerCase();
          const beforeState = String(imageChange.before || "")
            .toLowerCase()
            .replace(/_/g, " ");
          const afterState = String(imageChange.after || "")
            .toLowerCase()
            .replace(/_/g, " ");
          if (action === "reemplazada") {
            parts.push("Imagen: reemplazada");
          } else if (beforeState && afterState && beforeState !== afterState) {
            parts.push(`Imagen: ${beforeState} -> ${afterState}`);
          } else if (
            imageChange.before_hash &&
            imageChange.after_hash &&
            imageChange.before_hash !== imageChange.after_hash
          ) {
            parts.push("Imagen: contenido actualizado");
          } else if (action === "eliminada") {
            parts.push("Imagen: eliminada");
          } else if (action === "cargada") {
            parts.push("Imagen: cargada");
          }
          const beforeMime = String(imageChange.before_mime || "")
            .trim()
            .toLowerCase();
          const afterMime = String(imageChange.after_mime || "")
            .trim()
            .toLowerCase();
          if (beforeMime && afterMime && beforeMime !== afterMime) {
            parts.push(`Formato imagen: ${beforeMime} -> ${afterMime}`);
          }
        }
        if (parts.length) {
          return parts.join(" | ");
        }
      }
      if (eventType === "precio_actualizado") {
        const beforePrice = Number(details?.precio_anterior);
        const afterPrice = Number(details?.precio_nuevo);
        if (Number.isFinite(beforePrice) && Number.isFinite(afterPrice)) {
          const deltaPrice = afterPrice - beforePrice;
          const deltaAbs = this.formatCurrency(Math.abs(deltaPrice));
          const deltaLabel = `${deltaPrice >= 0 ? "+" : "-"}${deltaAbs}`;
          const reasonText = details?.motivo
            ? ` | Motivo: ${details.motivo}`
            : "";
          return `Precio: ${this.formatCurrency(beforePrice)} -> ${this.formatCurrency(afterPrice)} (${deltaLabel})${reasonText}`;
        }
      }
      if (
        eventType === "stock_ajustado" ||
        eventType === "inventario_movimiento"
      ) {
        const beforeStock = Number(details?.stock_anterior);
        const afterStock = Number(details?.stock_nuevo);
        const quantity = Number(details?.cantidad);
        const values = [];
        if (Number.isFinite(beforeStock) && Number.isFinite(afterStock)) {
          values.push(
            `Stock: ${this.formatNumber(beforeStock)} -> ${this.formatNumber(afterStock)}`,
          );
        }
        if (Number.isFinite(quantity)) {
          values.push(
            `Movimiento: ${quantity >= 0 ? "+" : ""}${this.formatNumber(quantity)}`,
          );
        }
        if (details?.motivo) {
          values.push(`Motivo: ${details.motivo}`);
        }
        if (values.length) {
          return values.join(" | ");
        }
      }
      return entry?.description || "-";
    },

    resolveAuditUserLabel(entry) {
      if (entry?.actor_name) {
        return entry.actor_name;
      }
      if (entry?.actor_username) {
        return entry.actor_username;
      }
      const actorId = Number(entry?.actor_user_id || 0);
      if (Number.isFinite(actorId) && actorId > 0) {
        return `usuario#${actorId}`;
      }
      return "Sin registro";
    },

    renderAuditTrail(events, summary = null) {
      if (!this.dom.auditTable) {
        return;
      }
      this.clearTableSkeleton(this.dom.auditTable);
      const rows = Array.isArray(events) ? events : [];
      if (!rows.length) {
        this.dom.auditTable.innerHTML =
          '<tr><td colspan="6" class="text-center text-muted">No hay eventos para el filtro seleccionado.</td></tr>';
        this.applyTableLabels(this.dom.auditTable);
      } else {
        this.dom.auditTable.innerHTML = rows
          .map((entry) => {
            const action = String(entry.event_type || "").toLowerCase();
            const badgeClass = action.includes("eliminado")
              ? "bg-danger"
              : action.includes("creado")
                ? "bg-success"
                : action.includes("precio") || action.includes("stock")
                  ? "bg-warning text-dark"
                  : "bg-primary";
            const entityLabel =
              entry.entity_type && entry.entity_id
                ? `${entry.entity_type} #${entry.entity_id}`
                : entry.entity_type || "-";
            const detailLabel = this.formatAuditDetails(entry);
            const userLabel = this.resolveAuditUserLabel(entry);
            return `
            <tr>
              <td>${this.formatNumber(entry.id || 0)}</td>
              <td>${this.formatDateTime(entry.created_at)}</td>
              <td><span class="badge ${badgeClass}">${this.escape(entry.event_type || "-")}</span></td>
              <td>${this.escape(detailLabel)}</td>
              <td>${this.escape(entityLabel)}</td>
              <td>${this.escape(userLabel)}</td>
            </tr>
          `;
          })
          .join("");
        this.applyTableLabels(this.dom.auditTable);
      }
      if (!this.dom.auditSummary) {
        return;
      }
      const total = Number(summary?.total ?? rows.length) || 0;
      this.dom.auditSummary.textContent = `Eventos: ${this.formatNumber(total)}`;
    },

    openModal(key) {
      const modal = this.modals[key];
      modal?.show();
    },

    closeModal(key) {
      const modal = this.modals[key];
      modal?.hide();
    },

    openProductModal(product = null) {
      if (!this.dom.productForm) {
        return;
      }
      this.dom.productForm.reset();
      this.dom.productFormMessage?.classList.add("d-none");
      this.resetProductImageDraft(product);
      if (this.dom.productIvaHint) {
        this.dom.productIvaHint.textContent = `IVA vigente: ${this.formatNumber(this.getCurrentIvaRate())}%`;
      }
      if (product) {
        this.dom.productId.value = product.id;
        this.dom.productName.value = product.nombre || "";
        this.dom.productCategory.value = product.categoria || "";
        this.dom.productPrice.value = Number(
          product.precio_base ?? product.precio ?? 0,
        );
        if (this.dom.productIvaPercent) {
          this.dom.productIvaPercent.value = Number(
            product.iva_porcentaje ??
              product.iva_percent ??
              this.getCurrentIvaRate(),
          );
        }
        this.dom.productStock.value = Number(product.stock || 0);
        this.dom.productMinStock.value = Number(product.min_stock || 0);
      } else {
        this.dom.productId.value = "";
        if (this.dom.productIvaPercent) {
          this.dom.productIvaPercent.value = Number(this.getCurrentIvaRate());
        }
      }
      this.openModal("product");
    },

    async saveProduct() {
      if (!this.dom.productForm) {
        return;
      }
      const id = this.dom.productId.value
        ? Number(this.dom.productId.value)
        : null;
      const payload = {
        nombre: this.dom.productName.value.trim(),
        categoria: this.dom.productCategory.value.trim(),
        precio: Number(this.dom.productPrice.value),
        iva_percent: Number(this.dom.productIvaPercent?.value),
        stock: Number(this.dom.productStock.value),
        min_stock: Number(this.dom.productMinStock.value),
      };
      if (
        this.state.productImageDraft?.mode === "set" &&
        this.state.productImageDraft.dataUrl
      ) {
        payload.imagen_data_url = this.state.productImageDraft.dataUrl;
      } else if (this.state.productImageDraft?.mode === "clear") {
        payload.imagen_data_url = "";
      }
      if (
        !payload.nombre ||
        !payload.categoria ||
        Number.isNaN(payload.precio) ||
        Number.isNaN(payload.iva_percent) ||
        payload.iva_percent < 0 ||
        payload.iva_percent > 100 ||
        Number.isNaN(payload.stock) ||
        Number.isNaN(payload.min_stock)
      ) {
        this.setAlert(
          this.dom.productFormMessage,
          "Completa todos los campos del producto.",
          "warning",
        );
        return;
      }
      const url = id ? `/api/productos/${id}` : "/api/productos";
      const method = id ? "PUT" : "POST";
      try {
        this.setButtonBusy(this.dom.saveProductBtn, true);
        try {
          await this.fetchJson(url, { method, body: payload });
        } catch (error) {
          const ratio = error?.payload?.ratio;
          const maxRatio = error?.payload?.max_ratio;
          if (
            error.status === 409 &&
            ratio &&
            maxRatio &&
            window.confirm(
              "El cambio de precio supera el limite permitido. Deseas forzarlo?",
            )
          ) {
            const minLen = this.state.user?.price_force_reason_min_length || 10;
            const reason =
              window.prompt(
                `Describe el motivo del cambio (minimo ${minLen} caracteres):`,
              ) || "";
            if (reason.trim().length >= minLen) {
              await this.fetchJson(url, {
                method,
                body: { ...payload, force: true, force_reason: reason.trim() },
              });
            } else {
              this.setAlert(
                this.dom.productFormMessage,
                "El motivo es demasiado corto.",
                "warning",
              );
              return;
            }
          } else {
            throw error;
          }
        }
        this.closeModal("product");
        this.loadProducts?.(this.dom.productFilter?.value.trim() || "");
        this.queueSearch?.(this.dom.productSearch?.value.trim() || "");
      } catch (error) {
        const message =
          error?.payload?.error ||
          error?.message ||
          "No se pudo guardar el producto.";
        this.setAlert(this.dom.productFormMessage, message, "danger");
      } finally {
        this.setButtonBusy(this.dom.saveProductBtn, false);
      }
    },

    async deleteProduct(id) {
      if (
        !window.confirm(
          "Esta accion desactivara el producto y dejara de estar disponible para ventas. Deseas continuar?",
        )
      ) {
        return;
      }
      try {
        await this.fetchJson(`/api/productos/${id}`, { method: "DELETE" });
        this.loadProducts?.(this.dom.productFilter?.value.trim() || "");
        this.queueSearch?.(this.dom.productSearch?.value.trim() || "");
      } catch (error) {
        console.error("No se pudo desactivar el producto", error);
        window.alert("No se pudo desactivar el producto.");
      }
    },

    async setProductActive(id, active) {
      const actionLabel = active ? "activar" : "desactivar";
      if (!window.confirm(`Deseas ${actionLabel} este producto?`)) {
        return;
      }
      try {
        await this.fetchJson(`/api/productos/${id}/estado`, {
          method: "PUT",
          body: { activo: active },
        });
        this.loadProducts?.(this.dom.productFilter?.value.trim() || "");
        this.queueSearch?.(this.dom.productSearch?.value.trim() || "");
      } catch (error) {
        console.error("No se pudo actualizar estado del producto", error);
        window.alert(`No se pudo ${actionLabel} el producto.`);
      }
    },

    openMinStockModal(product) {
      if (!product) {
        return;
      }
      if (this.dom.minStockProductId) {
        this.dom.minStockProductId.value = product.id;
      }
      if (this.dom.minStockProductName) {
        this.dom.minStockProductName.value = product.nombre || "";
      }
      if (this.dom.minStockValue) {
        this.dom.minStockValue.value = Number(product.min_stock || 0);
      }
      this.dom.minStockFormMessage?.classList.add("d-none");
      this.openModal("minStock");
    },

    async saveMinStock() {
      const id = Number(this.dom.minStockProductId?.value);
      const value = Number(this.dom.minStockValue?.value);
      if (!id || Number.isNaN(value) || value < 0) {
        this.setAlert(
          this.dom.minStockFormMessage,
          "Ingresa un minimo valido.",
          "warning",
        );
        return;
      }
      try {
        this.setButtonBusy(this.dom.saveMinStockBtn, true);
        await this.fetchJson(`/api/productos/${id}/minimo`, {
          method: "PUT",
          body: { min_stock: value },
        });
        this.closeModal("minStock");
        this.loadProducts?.(this.dom.productFilter?.value.trim() || "");
        this.queueSearch?.(this.dom.productSearch?.value.trim() || "");
      } catch (error) {
        const message =
          error?.payload?.error ||
          error?.message ||
          "No se pudo guardar el minimo.";
        this.setAlert(this.dom.minStockFormMessage, message, "danger");
      } finally {
        this.setButtonBusy(this.dom.saveMinStockBtn, false);
      }
    },

    defaultRoleCatalog() {
      return [
        {
          role: "admin",
          name: "Administrador",
          permissions: {
            dashboard_view: true,
            sales_view: true,
            sales_create: true,
            products_view: true,
            products_manage: true,
            reports_view: true,
            statistics_view: true,
            users_manage: true,
            audit_view: true,
            sessions_manage: true,
            backups_manage: true,
            ai_chat: true,
          },
          is_system: true,
        },
        {
          role: "gerente",
          name: "Gerente",
          permissions: {
            dashboard_view: true,
            sales_view: true,
            sales_create: true,
            products_view: true,
            products_manage: true,
            reports_view: true,
            statistics_view: true,
            users_manage: true,
            audit_view: false,
            sessions_manage: false,
            backups_manage: true,
            ai_chat: true,
          },
          is_system: true,
        },
        {
          role: "auditador",
          name: "Auditador",
          permissions: {
            dashboard_view: false,
            sales_view: false,
            sales_create: false,
            products_view: false,
            products_manage: false,
            reports_view: false,
            statistics_view: false,
            users_manage: false,
            audit_view: true,
            sessions_manage: false,
            backups_manage: false,
            ai_chat: false,
          },
          is_system: true,
        },
        {
          role: "vendedor",
          name: "Vendedor",
          permissions: {
            dashboard_view: true,
            sales_view: true,
            sales_create: true,
            products_view: true,
            products_manage: false,
            reports_view: false,
            statistics_view: false,
            users_manage: false,
            audit_view: false,
            sessions_manage: false,
            backups_manage: false,
            ai_chat: true,
          },
          is_system: true,
        },
      ];
    },

    renderUserRoleOptions(selectedRole = "vendedor") {
      if (!this.dom.userRole) {
        return;
      }
      const catalog =
        Array.isArray(this.state.roles) && this.state.roles.length
          ? this.state.roles
          : this.defaultRoleCatalog();
      const normalizedCatalog = catalog
        .map((item) => ({
          role: String(item.role || "")
            .trim()
            .toLowerCase(),
          name: String(item.name || item.role || "").trim(),
        }))
        .filter((item) => item.role);
      const currentRole = String(this.state.user?.role || "").toLowerCase();
      const canAssignAdminRole = currentRole === "admin";
      const options = [];
      normalizedCatalog.forEach((item) => {
        if (!canAssignAdminRole && item.role === "admin") {
          return;
        }
        options.push(
          `<option value="${this.escape(item.role)}">${this.escape(item.name || item.role)}</option>`,
        );
      });
      const normalizedSelected = String(selectedRole || "")
        .trim()
        .toLowerCase();
      if (
        normalizedSelected &&
        normalizedSelected !== "__new__" &&
        !normalizedCatalog.some((item) => item.role === normalizedSelected)
      ) {
        const fallbackLabel = normalizedSelected.replace(/_/g, " ");
        options.push(
          `<option value="${this.escape(normalizedSelected)}">${this.escape(fallbackLabel)}</option>`,
        );
      }
      options.push('<option value="__new__">+ Crear nuevo rol</option>');
      this.dom.userRole.innerHTML = options.join("");
      if (normalizedSelected === "__new__") {
        this.dom.userRole.value = "__new__";
      } else if (
        normalizedSelected &&
        Array.from(this.dom.userRole.options || []).some(
          (opt) => opt.value === normalizedSelected,
        )
      ) {
        this.dom.userRole.value = normalizedSelected;
      } else {
        this.dom.userRole.value = "vendedor";
      }
      this.toggleNewRolePanel();
    },

    toggleNewRolePanel() {
      const shouldShow = this.dom.userRole?.value === "__new__";
      if (!this.dom.userNewRolePanel) {
        return;
      }
      this.dom.userNewRolePanel.classList.toggle("d-none", !shouldShow);
      if (!shouldShow) {
        if (this.dom.userNewRoleName) {
          this.dom.userNewRoleName.value = "";
        }
        this.dom.rolePermissionInputs?.forEach((input) => {
          input.checked = false;
        });
        return;
      }
      const hasMarkedPermissions = this.dom.rolePermissionInputs?.some(
        (input) => input.checked,
      );
      if (!hasMarkedPermissions) {
        const starterPermissions = new Set([
          "dashboard_view",
          "sales_view",
          "sales_create",
          "products_view",
          "ai_chat",
        ]);
        this.dom.rolePermissionInputs?.forEach((input) => {
          input.checked = starterPermissions.has(input.value);
        });
      }
    },

    collectRolePermissions() {
      const permissions = {};
      this.dom.rolePermissionInputs?.forEach((input) => {
        permissions[input.value] = Boolean(input.checked);
      });
      return permissions;
    },

    sanitizeRoleCode(rawValue) {
      const ascii = String(rawValue || "")
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .toLowerCase()
        .replace(/[^a-z0-9_\s-]/g, "")
        .replace(/[\s-]+/g, "_")
        .replace(/_+/g, "_")
        .replace(/^_+|_+$/g, "");
      if (!/^[a-z][a-z0-9_]{2,31}$/.test(ascii)) {
        return "";
      }
      return ascii;
    },

    async loadRoles(options = {}) {
      if (!this.can("users_manage")) {
        return;
      }
      const silent = Boolean(options?.silent);
      try {
        const data = await this.fetchJson("/api/roles");
        this.state.roles = Array.isArray(data?.roles) ? data.roles : [];
        this.state.rolePermissionLabels = data?.permission_labels || {};
      } catch (error) {
        if (!silent) {
          const message =
            error?.payload?.error ||
            error?.message ||
            "No se pudieron cargar los roles.";
          window.alert(message);
        }
        this.state.roles = this.defaultRoleCatalog();
      } finally {
        this.renderUserRoleOptions(this.dom.userRole?.value || "vendedor");
      }
    },

    openUserModal(user = null) {
      if (!this.dom.userForm) {
        return;
      }
      this.dom.userForm.reset();
      if (!(this.state.roles || []).length) {
        this.loadRoles({ silent: true });
      }
      this.renderUserRoleOptions(user?.role || "vendedor");
      if (this.dom.userFormMessage) {
        this.dom.userFormMessage.classList.add("d-none");
        this.dom.userFormMessage.textContent = "";
      }
      if (this.dom.userPassword) {
        this.dom.userPassword.value = "";
        this.dom.userPassword.placeholder = user
          ? "Deja vacio para mantener"
          : "Minimo 8 caracteres, usa mayuscula, minuscula, numero y simbolo";
      }
      if (this.dom.userId) {
        this.dom.userId.value = user ? user.id : "";
      }
      if (user) {
        this.dom.userUsername.value = user.username || "";
        this.dom.userNameInput.value = user.name || "";
        this.dom.userRole.value = (user.role || "vendedor").toLowerCase();
        this.dom.userActive.checked = Boolean(user.activo);
        this.setAlert(
          this.dom.userFormMessage,
          `Deja la contrasena vacia para mantenerla. ${this.passwordPolicyMessage}`,
          "info",
        );
      } else {
        this.dom.userRole.value = "vendedor";
        this.dom.userActive.checked = true;
        this.setAlert(
          this.dom.userFormMessage,
          this.passwordPolicyMessage,
          "info",
        );
      }
      this.toggleNewRolePanel();
      this.openModal("user");
    },

    async saveUser() {
      const id = this.dom.userId?.value ? Number(this.dom.userId.value) : null;
      const payload = {
        username: this.dom.userUsername?.value.trim(),
        name: this.dom.userNameInput?.value.trim(),
      };
      const selectedRole = this.dom.userRole?.value || "vendedor";
      const passwordRaw = this.dom.userPassword?.value || "";
      if (this.dom.userFormMessage) {
        this.dom.userFormMessage.classList.add("d-none");
        this.dom.userFormMessage.textContent = "";
      }
      if (!payload.username) {
        this.setAlert(
          this.dom.userFormMessage,
          "El usuario es obligatorio.",
          "warning",
        );
        return;
      }
      const passwordCheck = this.validatePasswordStrength(passwordRaw, {
        required: !id,
      });
      if (!passwordCheck.ok) {
        this.setAlert(
          this.dom.userFormMessage,
          passwordCheck.message,
          "danger",
        );
        return;
      }
      if (passwordCheck.value) {
        payload.password = passwordCheck.value;
      }
      try {
        this.setButtonBusy(this.dom.saveUserBtn, true);
        if (selectedRole === "__new__") {
          const roleRawName = this.dom.userNewRoleName?.value?.trim() || "";
          const roleCode = this.sanitizeRoleCode(roleRawName);
          if (!roleCode) {
            this.setAlert(
              this.dom.userFormMessage,
              "Nombre de rol invalido. Usa letras, numeros y guion bajo (3 a 32 caracteres).",
              "warning",
            );
            return;
          }
          const permissions = this.collectRolePermissions();
          if (!Object.values(permissions).some(Boolean)) {
            this.setAlert(
              this.dom.userFormMessage,
              "Selecciona al menos un permiso para el nuevo rol.",
              "warning",
            );
            return;
          }
          const roleResponse = await this.fetchJson("/api/roles", {
            method: "POST",
            body: {
              role: roleCode,
              name: roleRawName,
              permissions,
            },
          });
          payload.role = roleResponse?.role || roleCode;
          await this.loadRoles({ silent: true });
        } else {
          payload.role = selectedRole;
        }
        if (id) {
          await this.fetchJson(`/api/usuarios/${id}`, {
            method: "PUT",
            body: payload,
          });
          await this.fetchJson(`/api/usuarios/${id}/estado`, {
            method: "PUT",
            body: { activo: this.dom.userActive.checked },
          });
        } else {
          const created = await this.fetchJson("/api/usuarios", {
            method: "POST",
            body: payload,
          });
          const newUserId = Number(created?.id || 0);
          if (newUserId > 0 && !this.dom.userActive.checked) {
            await this.fetchJson(`/api/usuarios/${newUserId}/estado`, {
              method: "PUT",
              body: { activo: false },
            });
          }
        }
        this.closeModal("user");
        this.loadUsers();
      } catch (error) {
        const message =
          error?.payload?.error ||
          error?.message ||
          "No se pudo guardar el usuario.";
        this.setAlert(this.dom.userFormMessage, message, "danger");
      } finally {
        this.setButtonBusy(this.dom.saveUserBtn, false);
      }
    },

    validatePasswordStrength(password, options = {}) {
      const required = Boolean(options.required);
      const trimmed = (password || "").trim();
      if (!trimmed) {
        if (required) {
          return { ok: false, message: "La contrasena es obligatoria." };
        }
        return { ok: true, value: "" };
      }
      const checks = [
        { test: trimmed.length >= PASSWORD_MIN_LENGTH },
        { test: /[A-Z]/.test(trimmed) },
        { test: /[a-z]/.test(trimmed) },
        { test: /[0-9]/.test(trimmed) },
        { test: /[^A-Za-z0-9]/.test(trimmed) },
      ];
      if (checks.every((item) => item.test)) {
        return { ok: true, value: trimmed };
      }
      return { ok: false, message: this.passwordPolicyMessage };
    },

    async loadUsers() {
      if (!this.can("users_manage")) {
        return;
      }
      if (this.dom.usersTable) {
        this.showTableSkeleton(this.dom.usersTable);
      }
      try {
        await this.loadRoles({ silent: true });
        const users = await this.fetchJson("/api/usuarios");
        this.state.users = Array.isArray(users) ? users : [];
        this.renderUsers(this.state.users);
      } catch (error) {
        console.error("No se pudieron cargar los usuarios", error);
        if (this.dom.usersTable) {
          this.clearTableSkeleton(this.dom.usersTable);
          this.dom.usersTable.innerHTML =
            '<tr><td colspan="5" class="text-center text-muted">No se pudieron cargar los usuarios.</td></tr>';
          this.applyTableLabels(this.dom.usersTable);
        }
      }
    },

    renderUsers(users) {
      if (!this.dom.usersTable) {
        return;
      }
      this.clearTableSkeleton(this.dom.usersTable);
      if (!users?.length) {
        this.dom.usersTable.innerHTML =
          '<tr><td colspan="5" class="text-center text-muted">Sin usuarios registrados.</td></tr>';
        this.applyTableLabels(this.dom.usersTable);
        return;
      }
      this.dom.usersTable.innerHTML = users
        .map((user) => {
          const badge = user.activo
            ? '<span class="badge bg-success">Activo</span>'
            : '<span class="badge bg-secondary">Inactivo</span>';
          const toggleLabel = user.activo ? "Desactivar" : "Activar";
          const toggleValue = user.activo ? "1" : "0";
          const roleCode = (user.role || "vendedor").toLowerCase();
          const roleFromCatalog = (this.state.roles || []).find(
            (item) => String(item.role || "").toLowerCase() === roleCode,
          );
          const roleLabel =
            user.role_name ||
            roleFromCatalog?.name ||
            (roleCode === "admin"
              ? "Administrador"
              : roleCode === "gerente"
                ? "Gerente"
                : roleCode === "auditador"
                  ? "Auditador"
                : roleCode === "vendedor"
                  ? "Vendedor"
                  : roleCode.replace(/_/g, " "));
          const isSelf = this.state.user && this.state.user.id === user.id;
          const isCurrentSuperuser =
            String(this.state.user?.role || "").toLowerCase() === "admin";
          const isAdminTarget = roleCode === "admin";
          const protectedByHierarchy = isAdminTarget && !isCurrentSuperuser;
          return `
          <tr data-id="${user.id}">
            <td>${this.escape(user.username)}</td>
            <td>${this.escape(user.name || "-")}</td>
            <td>${this.escape(roleLabel)}</td>
            <td>${badge}</td>
            <td class="text-end">
              <button class="btn btn-sm btn-outline-primary me-1" data-action="edit" ${protectedByHierarchy ? "disabled" : ""}>Editar</button>
              <button class="btn btn-sm btn-outline-secondary" data-action="toggle" data-active="${toggleValue}" ${isSelf || protectedByHierarchy ? "disabled" : ""}>${toggleLabel}</button>
            </td>
          </tr>
        `;
        })
        .join("");
      this.applyTableLabels(this.dom.usersTable);
    },

    async toggleUserActive(id, active) {
      if (!active && !window.confirm("Deseas desactivar este usuario?")) {
        return;
      }
      try {
        await this.fetchJson(`/api/usuarios/${id}/estado`, {
          method: "PUT",
          body: { activo: active },
        });
        this.loadUsers();
      } catch (error) {
        console.error("No se pudo actualizar el usuario", error);
        const message =
          error?.payload?.error ||
          error?.message ||
          "No se pudo actualizar el usuario.";
        window.alert(message);
      }
    },

    async generateReport(options = {}) {
      const silent = Boolean(options?.silent);
      if (!this.can("reports_view")) {
        return;
      }
      if (!this.dom.reportDateFrom || !this.dom.reportDateTo) {
        return;
      }
      const from = this.dom.reportDateFrom.value;
      const to = this.dom.reportDateTo.value;
      if (!from || !to) {
        if (!silent) {
          window.alert("Selecciona un rango de fechas.");
        }
        return;
      }
      this.showTableSkeleton(this.dom.salesReportTable);
      if (this.dom.reportSummary) {
        this.setAriaBusy(this.dom.reportSummary, true);
        this.dom.reportSummary.innerHTML = "";
      }
      if (this.dom.generateReportBtn) {
        this.setButtonBusy(this.dom.generateReportBtn, true);
      }
      try {
        const data = await this.fetchJson(
          `/api/reportes/ventas?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`,
        );
        this.state.reportData = data;
        this.renderReport(data);
      } catch (error) {
        const message =
          error?.payload?.error ||
          error?.message ||
          "No se pudo generar el reporte.";
        if (!silent) {
          window.alert(message);
        }
        if (this.dom.salesReportTable) {
          this.clearTableSkeleton(this.dom.salesReportTable);
          this.dom.salesReportTable.innerHTML =
            '<tr><td colspan="6" class="text-center text-muted">No se pudo generar el reporte.</td></tr>';
          this.applyTableLabels(this.dom.salesReportTable);
        }
        if (this.dom.reportSummary) {
          this.dom.reportSummary.innerHTML =
            '<div class="alert alert-warning mb-3">No se pudo obtener el resumen del periodo seleccionado.</div>';
        }
      } finally {
        this.clearTableSkeleton(this.dom.salesReportTable);
        if (this.dom.reportSummary) {
          this.setAriaBusy(this.dom.reportSummary, false);
        }
        if (this.dom.generateReportBtn) {
          this.setButtonBusy(this.dom.generateReportBtn, false);
        }
      }
    },

    async exportSalesReport(format = "pdf") {
      if (!this.can("reports_view")) {
        return;
      }
      const selectedFormat =
        String(format || "").toLowerCase() === "excel" ? "excel" : "pdf";
      const from = this.dom.reportDateFrom?.value || "";
      const to = this.dom.reportDateTo?.value || "";
      if (!from || !to) {
        window.alert("Selecciona un rango de fechas para exportar.");
        return;
      }
      const button =
        selectedFormat === "excel"
          ? this.dom.reportExportExcelBtn
          : this.dom.reportExportPdfBtn;
      const params = new URLSearchParams({
        from,
        to,
        format: selectedFormat,
      });
      try {
        this.setButtonBusy(button, true);
        await this.downloadApiFile(
          `/api/reportes/ventas/export?${params.toString()}`,
          `reporte-ventas.${selectedFormat === "excel" ? "xlsx" : "pdf"}`,
        );
      } catch (error) {
        const message =
          error?.payload?.error ||
          error?.message ||
          "No se pudo exportar el reporte de ventas.";
        window.alert(message);
      } finally {
        this.setButtonBusy(button, false);
      }
    },

    async loadRecentSales(options = {}) {
      const silent = Boolean(options?.silent);
      if (!this.can("sales_view") || !this.dom.recentSalesTable) {
        return;
      }
      const button = options?.button || this.dom.refreshRecentSalesBtn;
      if (button) {
        this.setButtonBusy(button, true);
      }
      try {
        const data = await this.fetchJson("/api/ventas/recientes?limit=20");
        this.renderRecentSales(data);
      } catch (error) {
        const message =
          error?.payload?.error ||
          error?.message ||
          "No se pudieron cargar las ventas recientes.";
        if (!silent) {
          window.alert(message);
        }
        this.dom.recentSalesTable.innerHTML =
          '<tr><td colspan="7" class="text-center text-muted">No se pudieron cargar las ventas recientes.</td></tr>';
        this.applyTableLabels(this.dom.recentSalesTable);
      } finally {
        if (button) {
          this.setButtonBusy(button, false);
        }
      }
    },

    getSaleStatusBadgeHtml(venta) {
      if (venta?.anulada) {
        return '<span class="badge text-bg-danger">Deshabilitada</span>';
      }
      if (venta?.anulacion_autorizada) {
        return '<span class="badge text-bg-warning">Habilitada</span>';
      }
      return '<span class="badge text-bg-success">Activa</span>';
    },

    renderRecentSales(data) {
      if (!this.dom.recentSalesTable) {
        return;
      }
      const ventas = Array.isArray(data?.ventas) ? data.ventas : [];
      if (this.dom.recentSalesMessage) {
        this.dom.recentSalesMessage.textContent = ventas.length
          ? "Ventas recientes disponibles para consulta y correccion controlada."
          : "No hay ventas recientes para mostrar.";
      }
      if (!ventas.length) {
        this.dom.recentSalesTable.innerHTML =
          '<tr><td colspan="7" class="text-center text-muted">No hay ventas recientes.</td></tr>';
        this.applyTableLabels(this.dom.recentSalesTable);
        return;
      }
      this.dom.recentSalesTable.innerHTML = ventas
        .map(
          (venta) => `
            <tr data-id="${venta.id}">
              <td>#${venta.id}</td>
              <td>${this.formatDateTime(venta.fecha)}</td>
              <td>${this.escape(venta.vendedor || venta.vendedor_nombre || "-")}</td>
              <td class="text-uppercase">${this.escape(venta.metodo_pago || "-")}</td>
              <td>${this.formatCurrency(venta.total || 0)}</td>
              <td>${this.getSaleStatusBadgeHtml(venta)}</td>
              <td class="text-end">
                <button class="btn btn-sm btn-outline-primary" data-action="detail">Detalle</button>
              </td>
            </tr>
          `,
        )
        .join("");
      this.applyTableLabels(this.dom.recentSalesTable);
    },

    renderReport(data) {
      if (!data) {
        return;
      }
      this.clearTableSkeleton(this.dom.salesReportTable);
      if (this.dom.reportSummary) {
        const resumen = data.resumen || {};
        const ventas = Array.isArray(data.ventas) ? data.ventas : [];
        const disabledCount = ventas.filter((venta) => Boolean(venta?.anulada)).length;
        const enabledCount = ventas.filter(
          (venta) => !venta?.anulada && Boolean(venta?.anulacion_autorizada),
        ).length;
        this.dom.reportSummary.innerHTML = `
          <div class="alert alert-info mb-3">
            Ventas: <strong>${this.formatNumber(resumen.ventas_registradas || 0)}</strong> |
            Deshabilitadas: <strong>${this.formatNumber(disabledCount)}</strong> |
            Habilitadas: <strong>${this.formatNumber(enabledCount)}</strong> |
            Productos vendidos: <strong>${this.formatNumber(resumen.total_productos || 0)}</strong> |
            Total: <strong>${this.formatCurrency(resumen.monto_total || 0)}</strong>
          </div>
        `;
      }
      if (this.dom.salesReportTable) {
        const ventas = data.ventas || [];
        if (!ventas.length) {
          this.dom.salesReportTable.innerHTML =
            '<tr><td colspan="7" class="text-center text-muted">No hay ventas para el periodo.</td></tr>';
          this.applyTableLabels(this.dom.salesReportTable);
        } else {
          this.dom.salesReportTable.innerHTML = ventas
            .map(
              (venta) => `
            <tr data-id="${venta.id}">
              <td>#${venta.id}</td>
              <td>${this.formatDateTime(venta.fecha)}</td>
              <td>${this.escape(venta.vendedor || "-")}</td>
              <td class="text-uppercase">${this.escape(venta.metodo_pago || "-")}</td>
              <td>${this.formatCurrency(venta.total || 0)}</td>
              <td>${this.getSaleStatusBadgeHtml(venta)}</td>
              <td class="text-end">
                <button class="btn btn-sm btn-outline-primary" data-action="detail">Detalle</button>
              </td>
            </tr>
          `,
            )
            .join("");
          this.applyTableLabels(this.dom.salesReportTable);
        }
      }
      if (this.dom.reportSummary) {
        this.setAriaBusy(this.dom.reportSummary, false);
      }
    },

    setSaleVoidMessage(message = "", tone = "muted") {
      if (!this.dom.saleVoidMessage) {
        return;
      }
      this.dom.saleVoidMessage.textContent = message || "";
      this.dom.saleVoidMessage.className = "small mt-2";
      if (tone === "danger") {
        this.dom.saleVoidMessage.classList.add("text-danger");
      } else if (tone === "success") {
        this.dom.saleVoidMessage.classList.add("text-success");
      } else if (tone === "warning") {
        this.dom.saleVoidMessage.classList.add("text-warning");
      } else {
        this.dom.saleVoidMessage.classList.add("text-muted");
      }
    },

    renderSaleVoidControls(data) {
      const sale = data?.venta || {};
      const capabilities = data?.capabilities || {};
      const currentRole = String(this.state.user?.role || "")
        .trim()
        .toLowerCase();
      if (this.dom.saleVoidKey) {
        this.dom.saleVoidKey.value = "";
      }
      this.setSaleVoidMessage("");
      if (this.dom.saleVoidManagerPanel) {
        this.dom.saleVoidManagerPanel.classList.add("d-none");
      }
      if (this.dom.saleVoidSellerPanel) {
        this.dom.saleVoidSellerPanel.classList.add("d-none");
      }
      if (this.dom.saleVoidControls) {
        this.dom.saleVoidControls.classList.remove("d-none");
      }
      if (this.dom.saleVoidStatus) {
        this.dom.saleVoidStatus.className = "alert mt-3";
      }
      if (sale.anulada) {
        const parts = ["Venta deshabilitada"];
        if (sale.anulada_en) {
          parts.push(`el ${this.formatDateTime(sale.anulada_en)}`);
        }
        if (sale.anulacion_motivo) {
          parts.push(`Motivo: ${sale.anulacion_motivo}`);
        }
        if (this.dom.saleVoidStatus) {
          this.dom.saleVoidStatus.textContent = parts.join(". ");
          this.dom.saleVoidStatus.classList.add("alert-danger");
          this.dom.saleVoidStatus.classList.remove("d-none");
        }
        if (this.dom.saleVoidControls) {
          this.dom.saleVoidControls.classList.add("d-none");
        }
        return;
      }
      let statusMessage = "Venta activa.";
      let statusTone = "alert-secondary";
      if (sale.anulacion_autorizada) {
        statusMessage =
          "Esta venta ya fue habilitada para que un vendedor la deshabilite.";
        statusTone = "alert-warning";
      } else if (currentRole === "vendedor") {
        statusMessage =
          "Si hubo un error, solicita al gerente que habilite esta venta antes de deshabilitarla.";
        statusTone = "alert-info";
      } else if (currentRole === "gerente") {
        statusMessage =
          "Como gerente puedes habilitar solo esta venta puntual usando la clave de autorizacion.";
        statusTone = "alert-info";
      } else if (currentRole === "admin") {
        statusMessage =
          "Como administrador puedes deshabilitar la venta directamente o habilitarla para el vendedor.";
        statusTone = "alert-info";
      }
      if (this.dom.saleVoidStatus) {
        this.dom.saleVoidStatus.textContent = statusMessage;
        this.dom.saleVoidStatus.classList.add(statusTone);
        this.dom.saleVoidStatus.classList.remove("d-none");
      }
      if (capabilities.can_authorize_void && currentRole !== "admin") {
        this.dom.saleVoidManagerPanel?.classList.remove("d-none");
      }
      if (capabilities.can_void) {
        if (this.dom.voidSaleBtn) {
          this.dom.voidSaleBtn.textContent =
            currentRole === "admin"
              ? "Deshabilitar venta"
              : "Deshabilitar venta habilitada";
        }
        this.dom.saleVoidSellerPanel?.classList.remove("d-none");
      }
      if (
        !capabilities.can_authorize_void &&
        !capabilities.can_void &&
        !sale.anulacion_autorizada &&
        this.dom.saleVoidControls
      ) {
        this.dom.saleVoidControls.classList.add("d-none");
      }
    },

    async authorizeCurrentSaleVoid() {
      const saleId = Number(this.state.currentSaleDetail?.venta?.id || 0);
      const key = this.dom.saleVoidKey?.value?.trim() || "";
      if (!saleId) {
        return;
      }
      if (!key) {
        this.setSaleVoidMessage("Ingresa la clave del gerente.", "warning");
        return;
      }
      try {
        this.setButtonBusy(this.dom.authorizeSaleVoidBtn, true);
        const data = await this.fetchJson(
          `/api/ventas/${saleId}/autorizar-deshabilitacion`,
          {
            method: "POST",
            body: { clave: key },
          },
        );
        await this.openSaleDetail(saleId);
        await this.loadRecentSales({ silent: true });
        this.setSaleVoidMessage(
          data?.message || "Venta habilitada correctamente.",
          "success",
        );
      } catch (error) {
        const message =
          error?.payload?.error ||
          error?.message ||
          "No se pudo habilitar la venta.";
        this.setSaleVoidMessage(message, "danger");
      } finally {
        this.setButtonBusy(this.dom.authorizeSaleVoidBtn, false);
      }
    },

    async disableCurrentSale() {
      const saleId = Number(this.state.currentSaleDetail?.venta?.id || 0);
      if (!saleId) {
        return;
      }
      const confirmed = window.confirm(
        "Esta accion deshabilitara la venta, la sacara de los totales y devolvera el stock. ¿Continuar?",
      );
      if (!confirmed) {
        return;
      }
      const reason =
        window.prompt("Motivo de la deshabilitacion (opcional):", "") || "";
      try {
        this.setButtonBusy(this.dom.voidSaleBtn, true);
        const data = await this.fetchJson(`/api/ventas/${saleId}/deshabilitar`, {
          method: "POST",
          body: { motivo: reason },
        });
        await this.openSaleDetail(saleId);
        await this.loadRecentSales({ silent: true });
        await this.loadDashboard({ silent: true });
        if (this.can("products_view")) {
          await this.loadProducts?.(this.dom.productFilter?.value.trim() || "");
        }
        this.queueSearch?.(this.dom.productSearch?.value.trim() || "");
        if (this.can("reports_view") && this.state.reportData) {
          await this.generateReport({ silent: true });
        }
        this.setSaleVoidMessage(
          data?.message || "Venta deshabilitada correctamente.",
          "success",
        );
      } catch (error) {
        const message =
          error?.payload?.error ||
          error?.message ||
          "No se pudo deshabilitar la venta.";
        this.setSaleVoidMessage(message, "danger");
      } finally {
        this.setButtonBusy(this.dom.voidSaleBtn, false);
      }
    },

    async openSaleDetail(id) {
      if (this.dom.saleDetailItems) {
        this.showTableSkeleton(this.dom.saleDetailItems, 2);
      }
      try {
        const data = await this.fetchJson(`/api/ventas/${id}`);
        if (!data?.venta) {
          if (this.dom.saleDetailItems) {
            this.clearTableSkeleton(this.dom.saleDetailItems);
          }
          window.alert("No se encontro la venta.");
          return;
        }
        this.state.currentSaleDetail = data;
        if (this.dom.saleIdHeader) {
          this.dom.saleIdHeader.textContent = id;
        }
        if (this.dom.saleDate) {
          this.dom.saleDate.textContent = this.formatDateTime(data.venta.fecha);
        }
        if (this.dom.saleSubtotalDetail) {
          this.dom.saleSubtotalDetail.textContent = this.formatCurrency(
            data.venta.subtotal || 0,
          );
        }
        if (this.dom.saleIvaDetail) {
          const ivaRate = Number(data.venta.iva_porcentaje);
          const ivaLabel = Number.isFinite(ivaRate)
            ? ` (${this.formatNumber(ivaRate)}%)`
            : "";
          this.dom.saleIvaDetail.textContent = `${this.formatCurrency(data.venta.iva_total || 0)}${ivaLabel}`;
        }
        if (this.dom.saleTotalDetail) {
          this.dom.saleTotalDetail.textContent = this.formatCurrency(
            data.venta.total || 0,
          );
        }
        if (this.dom.salePaymentMethod) {
          this.dom.salePaymentMethod.textContent = this.escape(
            data.venta.metodo_pago || "-",
          );
        }
        if (this.dom.saleDetailItems) {
          this.clearTableSkeleton(this.dom.saleDetailItems);
          const items = Array.isArray(data.items) ? data.items : [];
          if (!items.length) {
            this.dom.saleDetailItems.innerHTML =
              '<tr><td colspan="4" class="text-center text-muted">Sin productos registrados en la venta.</td></tr>';
          } else {
            this.dom.saleDetailItems.innerHTML = items
              .map(
                (item) => `
              <tr>
                <td>${this.escape(item.nombre)}</td>
                <td>${this.formatNumber(item.cantidad || 0)}</td>
                <td>${this.formatCurrency(item.precio || 0)}</td>
                <td>${this.formatCurrency(item.subtotal || item.precio * item.cantidad || 0)}</td>
              </tr>
            `,
              )
              .join("");
          }
          this.applyTableLabels(this.dom.saleDetailItems);
        }
        if (this.dom.saleRecommendations) {
          const rec = data.recomendaciones;
          const parts = [];
          if (rec) {
            const comboLines = Array.isArray(rec.combo_suggestions)
              ? rec.combo_suggestions
                  .map((item) => this.describeComboSuggestion(item))
                  .filter(Boolean)
              : [];
            if (comboLines.length) {
              parts.push(
                `<div class="mb-2"><strong>Combos:</strong><br>${comboLines.map((line) => this.escape(line)).join("<br>")}</div>`,
              );
            }
            const restockLines = Array.isArray(rec.restock_alerts)
              ? rec.restock_alerts
                  .map((item) => this.describeRestockAlert(item))
                  .filter(Boolean)
              : [];
            if (restockLines.length) {
              parts.push(
                `<div><strong>Reposicion:</strong><br>${restockLines.map((line) => this.escape(line)).join("<br>")}</div>`,
              );
            }
          }
          if (parts.length) {
            this.dom.saleRecommendations.innerHTML = parts.join("");
            this.dom.saleRecommendations.classList.remove("d-none");
          } else {
            this.dom.saleRecommendations.classList.add("d-none");
            this.dom.saleRecommendations.innerHTML = "";
          }
        }
        this.renderSaleVoidControls(data);
        this.openModal("saleDetail");
      } catch (error) {
        console.error("No se pudo obtener el detalle de la venta", error);
        window.alert("No se pudo obtener el detalle.");
        this.state.currentSaleDetail = null;
        if (this.dom.saleDetailItems) {
          this.clearTableSkeleton(this.dom.saleDetailItems);
          this.dom.saleDetailItems.innerHTML =
            '<tr><td colspan="4" class="text-center text-muted">No se pudieron cargar los detalles.</td></tr>';
          this.applyTableLabels(this.dom.saleDetailItems);
        }
      }
    },
  });

  Object.assign(App, {
    async generateStats(options = {}) {
      const silent = Boolean(options?.silent);
      if (!this.can("statistics_view")) {
        return;
      }
      const from = this.dom.statsDateFrom?.value || "";
      const to = this.dom.statsDateTo?.value || "";
      if (!from || !to) {
        if (!silent) {
          window.alert("Selecciona un rango de fechas.");
        }
        await this.loadDemandForecast({
          horizon: this.dom.forecastHorizonDays?.value,
          manageButton: false,
        });
        return;
      }
      if (new Date(from) > new Date(to)) {
        if (!silent) {
          window.alert('La fecha "Desde" no puede ser mayor que "Hasta".');
        }
        await this.loadDemandForecast({
          horizon: this.dom.forecastHorizonDays?.value,
          manageButton: false,
        });
        return;
      }
      if (this.dom.statsUnitsTable) {
        this.showTableSkeleton(this.dom.statsUnitsTable);
      }
      if (this.dom.generateStatsBtn) {
        this.setButtonBusy(this.dom.generateStatsBtn, true);
      }
      try {
        const params = new URLSearchParams({ from, to });
        const data = await this.fetchJson(
          `/api/estadisticas/productos-mas-vendidos?${params.toString()}`,
        );
        this.renderStats(data);
      } catch (error) {
        console.error("No se pudieron generar las estadisticas", error);
        if (!silent) {
          window.alert("No se pudieron generar las estadisticas.");
        }
        if (this.dom.statsUnitsTable) {
          this.clearTableSkeleton(this.dom.statsUnitsTable);
          this.dom.statsUnitsTable.innerHTML =
            '<tr><td colspan="2" class="text-center text-muted">No se pudieron cargar las estadisticas.</td></tr>';
          this.applyTableLabels(this.dom.statsUnitsTable);
        }
      } finally {
        this.clearTableSkeleton(this.dom.statsUnitsTable);
        if (this.dom.generateStatsBtn) {
          this.setButtonBusy(this.dom.generateStatsBtn, false);
        }
      }
      await this.loadDemandForecast({
        from,
        to,
        horizon: this.dom.forecastHorizonDays?.value,
        manageButton: false,
      });
    },

    async exportStatsReport(format = "pdf") {
      if (!this.can("statistics_view")) {
        return;
      }
      const selectedFormat =
        String(format || "").toLowerCase() === "excel" ? "excel" : "pdf";
      const from = this.dom.statsDateFrom?.value || "";
      const to = this.dom.statsDateTo?.value || "";
      if (!from || !to) {
        window.alert(
          "Selecciona un rango de fechas para exportar las estadisticas.",
        );
        return;
      }
      if (new Date(from) > new Date(to)) {
        window.alert('La fecha "Desde" no puede ser mayor que "Hasta".');
        return;
      }
      const button =
        selectedFormat === "excel"
          ? this.dom.statsExportExcelBtn
          : this.dom.statsExportPdfBtn;
      const params = new URLSearchParams({
        from,
        to,
        format: selectedFormat,
      });
      try {
        this.setButtonBusy(button, true);
        await this.downloadApiFile(
          `/api/estadisticas/productos-mas-vendidos/export?${params.toString()}`,
          `reporte-estadisticas.${selectedFormat === "excel" ? "xlsx" : "pdf"}`,
        );
      } catch (error) {
        const message =
          error?.payload?.error ||
          error?.message ||
          "No se pudo exportar el reporte estadistico.";
        window.alert(message);
      } finally {
        this.setButtonBusy(button, false);
      }
    },

    updateStatsFocus(
      topRevenue,
      focusIndex,
      chartRevenueTotal,
      source = "grafica",
      chartColors = [],
    ) {
      if (!Array.isArray(topRevenue) || !topRevenue.length) {
        if (this.dom.statsChartFocus) {
          this.dom.statsChartFocus.classList.add("d-none");
          this.dom.statsChartFocus.innerHTML = "";
        }
        return;
      }
      const safeIndex = Math.max(
        0,
        Math.min(Number(focusIndex) || 0, topRevenue.length - 1),
      );
      const item = topRevenue[safeIndex];
      const amount = Number(item?.ingresos || 0);
      const share =
        chartRevenueTotal > 0 ? (amount / chartRevenueTotal) * 100 : 0;
      const units = Number(item?.cantidad || 0);
      const color = String(
        chartColors[safeIndex % Math.max(chartColors.length, 1)] || "#2f58e7",
      );
      if (this.dom.statsChartFocus) {
        this.dom.statsChartFocus.style.setProperty("--stats-focus-accent", color);
        this.dom.statsChartFocus.style.setProperty(
          "--stats-focus-accent-soft",
          this.hexToRgba(color, 0.12),
        );
        this.dom.statsChartFocus.style.setProperty(
          "--stats-focus-accent-border",
          this.hexToRgba(color, 0.22),
        );
        this.dom.statsChartFocus.style.setProperty(
          "--stats-focus-accent-shadow",
          this.hexToRgba(color, 0.18),
        );
        this.dom.statsChartFocus.innerHTML = `
          <div class="d-flex align-items-center gap-2 mb-1">
            <span class="legend-dot" style="background:${color}"></span>
            <div class="stats-chart-focus-label">${this.escape(item?.nombre || "--")}</div>
          </div>
          <div class="stats-chart-focus-value">${this.formatCurrency(amount)}</div>
          <div class="stats-chart-focus-meta">
            <span>Participacion: ${this.formatDecimal(share, 1)}%</span>
            <span>${units > 0 ? `${this.formatNumber(units)} uds` : "Grupo consolidado"}</span>
          </div>
        `;
        this.dom.statsChartFocus.classList.remove("d-none");
      }
      if (this.dom.statsChartHint) {
        this.dom.statsChartHint.textContent = `Detalle activo: ${item?.nombre || "--"}`;
      }
      if (this.dom.statsLegend) {
        this.dom.statsLegend
          .querySelectorAll(".stats-legend-item")
          .forEach((entry) => {
            const itemIndex = Number(entry.dataset.statsIndex || -1);
            entry.classList.toggle("active", itemIndex === safeIndex);
          });
      }
    },

    setStatsChartActiveSlice(index, showTooltip = true) {
      const chart = this.charts?.categoriesPie;
      if (!chart) {
        return;
      }
      const safeIndex = Number(index);
      if (!Number.isFinite(safeIndex) || safeIndex < 0) {
        chart.setActiveElements([]);
        if (chart.tooltip) {
          chart.tooltip.setActiveElements([], { x: 0, y: 0 });
        }
        chart.update();
        return;
      }
      const activePoint = [{ datasetIndex: 0, index: safeIndex }];
      chart.setActiveElements(activePoint);
      if (chart.tooltip) {
        const arc = chart.getDatasetMeta(0)?.data?.[safeIndex];
        const point = arc?.getCenterPoint?.() || { x: 0, y: 0 };
        chart.tooltip.setActiveElements(showTooltip ? activePoint : [], point);
      }
      chart.update();
    },

    bindStatsLegendInteractions(
      topRevenue,
      chartRevenueTotal,
      chartColors = [],
    ) {
      if (!this.dom.statsLegend) {
        return;
      }
      const legendItems =
        this.dom.statsLegend.querySelectorAll(".stats-legend-item");
      legendItems.forEach((entry) => {
        const itemIndex = Number(entry.dataset.statsIndex || -1);
        const activate = () => {
          if (!Number.isFinite(itemIndex) || itemIndex < 0) {
            return;
          }
          this.updateStatsFocus(
            topRevenue,
            itemIndex,
            chartRevenueTotal,
            "leyenda",
            chartColors,
          );
          this.setStatsChartActiveSlice(itemIndex, true);
        };
        entry.addEventListener("mouseenter", activate);
        entry.addEventListener("focus", activate);
        entry.addEventListener("click", activate);
        entry.addEventListener("keydown", (evt) => {
          if (evt.key === "Enter" || evt.key === " ") {
            evt.preventDefault();
            activate();
          }
        });
      });
    },

    renderStats(data) {
      if (!data) {
        return;
      }
      this.clearTableSkeleton(this.dom.statsUnitsTable);
      const items = data.productos || [];
      if (this.dom.statsUnitsTable) {
        this.dom.statsUnitsTable.innerHTML = "";
      }
      if (this.dom.statsLegend) {
        this.dom.statsLegend.innerHTML = "";
      }
      if (this.dom.statsChartHint) {
        this.dom.statsChartHint.textContent =
          "Selecciona un segmento o una fila para ver el detalle.";
      }
      if (this.dom.statsChartFocus) {
        this.dom.statsChartFocus.classList.add("d-none");
        this.dom.statsChartFocus.innerHTML = "";
      }
      if (!items.length) {
        this.dom.statisticsEmpty?.classList.remove("d-none");
        this.dom.statisticsSummaryRow?.classList.add("d-none");
        this.dom.statisticsNote?.classList.add("d-none");
        if (this.dom.statsUnitsTable) {
          this.dom.statsUnitsTable.innerHTML =
            '<tr><td colspan="2" class="text-center text-muted">Sin datos disponibles.</td></tr>';
          this.applyTableLabels(this.dom.statsUnitsTable);
        }
        if (this.dom.statsLegend) {
          this.dom.statsLegend.classList.add("d-none");
        }
        if (this.dom.statsSummaryRevenue) {
          this.dom.statsSummaryRevenue.textContent = this.formatCurrency(0);
        }
        if (this.dom.statsSummaryUnits) {
          this.dom.statsSummaryUnits.textContent = this.formatNumber(0);
        }
        if (this.dom.statsSummaryTopProduct) {
          this.dom.statsSummaryTopProduct.textContent = "--";
          this.dom.statsSummaryTopProduct.title = "--";
        }
        if (this.dom.statsSummaryTopRevenue) {
          this.dom.statsSummaryTopRevenue.textContent = "--";
          this.dom.statsSummaryTopRevenue.title = "--";
        }
        this.destroyChart("categoriesPie");
        return;
      }
      const MAX_UNIT_ROWS = 7;
      const MAX_REVENUE_ITEMS = 6;
      const normalized = items.map((item) => ({
        nombre: item.nombre,
        cantidad: Number(item.cantidad || 0),
        ingresos: Number(item.ingresos || 0),
      }));
      const sortedByUnits = [...normalized].sort(
        (a, b) => b.cantidad - a.cantidad,
      );
      const sortedByRevenue = [...normalized].sort(
        (a, b) => b.ingresos - a.ingresos,
      );
      const topUnits = sortedByUnits.slice(0, MAX_UNIT_ROWS);
      const unitsRemainder = sortedByUnits.slice(MAX_UNIT_ROWS);
      const groupedUnitsTotal = unitsRemainder.reduce(
        (sum, item) => sum + item.cantidad,
        0,
      );
      if (groupedUnitsTotal > 0) {
        topUnits.push({
          nombre: "Otros",
          cantidad: groupedUnitsTotal,
          ingresos: 0,
        });
      }
      const topRevenue = sortedByRevenue.slice(0, MAX_REVENUE_ITEMS);
      const revenueRemainder = sortedByRevenue.slice(MAX_REVENUE_ITEMS);
      const groupedRevenueTotal = revenueRemainder.reduce(
        (sum, item) => sum + item.ingresos,
        0,
      );
      const chartColors = STATISTICS_CHART_PALETTE;
      if (groupedRevenueTotal > 0) {
        topRevenue.push({
          nombre: "Otros",
          cantidad: 0,
          ingresos: groupedRevenueTotal,
        });
      }
      const chartRevenueTotal = topRevenue.reduce(
        (sum, item) => sum + Number(item.ingresos || 0),
        0,
      );
      const groupedCount = unitsRemainder.length + revenueRemainder.length;
      if (this.dom.statisticsNote) {
        if (groupedCount > 0) {
          this.dom.statisticsNote.textContent = `Se agruparon ${groupedCount} productos adicionales en "Otros". Refina el periodo para mas detalle.`;
          this.dom.statisticsNote.classList.remove("d-none");
        } else {
          this.dom.statisticsNote.classList.add("d-none");
          this.dom.statisticsNote.textContent = "";
        }
      }
      if (this.dom.statsUnitsTable) {
        this.dom.statsUnitsTable.innerHTML = topUnits
          .map(
            (item, idx) => `
          <tr>
            <td>
              <div class="d-flex align-items-center gap-2">
                <span class="badge bg-secondary">${idx + 1}</span>
                <span>${this.escape(item.nombre)}</span>
              </div>
            </td>
            <td class="text-end fw-semibold">${this.formatNumber(item.cantidad)}</td>
          </tr>
        `,
          )
          .join("");
        this.applyTableLabels(this.dom.statsUnitsTable);
      }
      if (this.dom.statsLegend) {
        this.dom.statsLegend.innerHTML = topRevenue
          .map((item, idx) => {
            const accent = chartColors[idx % chartColors.length];
            const accentSoft = this.hexToRgba(accent, 0.1);
            const accentBorder = this.hexToRgba(accent, 0.22);
            const share = (Number(item.ingresos || 0) / Math.max(chartRevenueTotal, 1)) * 100;
            const width = Math.max(
              0,
              Math.min(
                100,
                share,
              ),
            ).toFixed(2);
            return `
          <div
            class="stats-legend-item"
            data-stats-index="${idx}"
            tabindex="0"
            role="button"
            aria-label="Ver detalle de ${this.escape(item.nombre)}"
            style="--legend-accent:${accent};--legend-accent-soft:${accentSoft};--legend-accent-border:${accentBorder};"
          >
            <div class="stats-legend-top">
              <div class="stats-legend-name">
                <span class="legend-dot" style="background:${accent}"></span>
                <span title="${this.escape(item.nombre)}">${this.escape(item.nombre)}</span>
              </div>
              <div class="stats-legend-value">${this.formatCurrency(item.ingresos)}</div>
            </div>
            <div class="stats-legend-bottom">
              <div class="stats-legend-bar">
                <span style="width:${width}%;background:${accent}"></span>
              </div>
              <div class="legend-share">${this.formatDecimal(share, 1)}%</div>
            </div>
          </div>
        `;
          })
          .join("");
        this.dom.statsLegend.classList.toggle(
          "d-none",
          topRevenue.length === 0,
        );
      }
      const totalUnitsFromApi = Number(data?.resumen?.total_unidades);
      const totalRevenueFromApi = Number(data?.resumen?.monto_total);
      const totalUnits = Number.isFinite(totalUnitsFromApi)
        ? totalUnitsFromApi
        : normalized.reduce((sum, item) => sum + item.cantidad, 0);
      const totalRevenue = Number.isFinite(totalRevenueFromApi)
        ? totalRevenueFromApi
        : normalized.reduce((sum, item) => sum + item.ingresos, 0);
      const topUnitsItem = sortedByUnits[0] || { nombre: "--" };
      const topRevenueItem = sortedByRevenue[0] || { nombre: "--" };
      this.dom.statisticsEmpty?.classList.add("d-none");
      this.dom.statisticsSummaryRow?.classList.remove("d-none");
      if (this.dom.statsSummaryRevenue) {
        this.dom.statsSummaryRevenue.textContent =
          this.formatCurrency(totalRevenue);
      }
      if (this.dom.statsSummaryUnits) {
        this.dom.statsSummaryUnits.textContent = this.formatNumber(totalUnits);
      }
      if (this.dom.statsSummaryTopProduct) {
        this.dom.statsSummaryTopProduct.textContent =
          topUnitsItem.nombre || "--";
        this.dom.statsSummaryTopProduct.title = topUnitsItem.nombre || "--";
      }
      if (this.dom.statsSummaryTopRevenue) {
        this.dom.statsSummaryTopRevenue.textContent =
          topRevenueItem.nombre || "--";
        this.dom.statsSummaryTopRevenue.title = topRevenueItem.nombre || "--";
      }
      this.destroyChart("categoriesPie");
      this.renderChart("categoriesPie", this.dom.categoriesPieChart, {
        type: "doughnut",
        data: {
          labels: topRevenue.map((item) => item.nombre),
          datasets: [
            {
              data: topRevenue.map((item) => item.ingresos),
              backgroundColor: topRevenue.map(
                (_, idx) => chartColors[idx % chartColors.length],
              ),
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          cutout: "48%",
          hoverOffset: 16,
          interaction: {
            mode: "nearest",
            intersect: false,
          },
          onHover: (_event, elements) => {
            if (!elements?.length) {
              return;
            }
            const point = elements[0];
            if (typeof point?.index !== "number") {
              return;
            }
            this.updateStatsFocus(
              topRevenue,
              point.index,
              chartRevenueTotal,
              "grafica",
              chartColors,
            );
          },
          plugins: {
            legend: {
              display: false,
            },
            tooltip: {
              displayColors: false,
              padding: 10,
              callbacks: {
                title: (ctx) =>
                  ctx?.[0]?.label ? `Producto: ${ctx[0].label}` : "Producto",
                label: (ctx) => `Ingreso: ${this.formatCurrency(ctx.parsed)}`,
                afterLabel: (ctx) => {
                  const current = Number(ctx?.parsed || 0);
                  const share =
                    chartRevenueTotal > 0
                      ? (current / chartRevenueTotal) * 100
                      : 0;
                  return `Participacion: ${this.formatDecimal(share, 1)}%`;
                },
              },
            },
          },
          elements: {
            arc: {
              borderColor: "#ffffff",
              borderWidth: 2,
            },
          },
        },
      });
      this.bindStatsLegendInteractions(
        topRevenue,
        chartRevenueTotal,
        chartColors,
      );
      this.updateStatsFocus(
        topRevenue,
        0,
        chartRevenueTotal,
        "grafica",
        chartColors,
      );
    },

    async loadDemandForecast(options = {}) {
      if (!this.can("statistics_view")) {
        return;
      }
      const from = options.from || this.dom.statsDateFrom?.value || "";
      const to = options.to || this.dom.statsDateTo?.value || "";
      const horizonRaw =
        options.horizon || this.dom.forecastHorizonDays?.value || "14";
      const horizon = Number(horizonRaw);
      if (!Number.isFinite(horizon) || horizon < 3 || horizon > 90) {
        if (this.dom.forecastSummary) {
          this.dom.forecastSummary.textContent =
            "Horizonte invalido. Usa un valor entre 3 y 90 dias.";
        }
        if (this.dom.forecastResultCount) {
          this.dom.forecastResultCount.textContent = "Sin resultados";
        }
        return;
      }
      if ((from && !to) || (!from && to)) {
        if (this.dom.forecastSummary) {
          this.dom.forecastSummary.textContent =
            "Para el pronostico define ambas fechas (desde y hasta).";
        }
        if (this.dom.forecastResultCount) {
          this.dom.forecastResultCount.textContent = "Sin resultados";
        }
        return;
      }
      if (this.dom.forecastTable) {
        this.showTableSkeleton(this.dom.forecastTable);
      }
      if (this.dom.forecastSummary) {
        this.dom.forecastSummary.textContent = "Calculando pronostico...";
      }
      if (this.dom.forecastResultCount) {
        this.dom.forecastResultCount.textContent = "Actualizando...";
      }
      if (this.dom.forecastModelBadges) {
        this.dom.forecastModelBadges.innerHTML = "";
      }
      const manageButton = options.manageButton !== false;
      if (manageButton && this.dom.refreshForecastBtn) {
        this.setButtonBusy(this.dom.refreshForecastBtn, true);
      }
      const params = new URLSearchParams({
        horizon: String(Math.round(horizon)),
        limit: "30",
      });
      if (from) {
        params.set("from", from);
      }
      if (to) {
        params.set("to", to);
      }
      try {
        const data = await this.fetchJson(
          `/api/ia/pronostico-demanda?${params.toString()}`,
        );
        this.state.forecastData = data;
        this.renderDemandForecast(data);
      } catch (error) {
        console.error("No se pudo cargar el pronostico de demanda", error);
        if (this.dom.forecastTable) {
          this.clearTableSkeleton(this.dom.forecastTable);
          this.dom.forecastTable.innerHTML =
            '<tr><td colspan="5" class="text-center text-muted">No se pudo cargar el pronostico.</td></tr>';
          this.applyTableLabels(this.dom.forecastTable);
        }
        if (this.dom.forecastModelSummary) {
          this.dom.forecastModelSummary.textContent =
            "No fue posible obtener informacion del modelo.";
          this.dom.forecastModelSummary.classList.remove("d-none");
        }
        if (this.dom.forecastModelBadges) {
          this.dom.forecastModelBadges.innerHTML = "";
        }
        if (this.dom.forecastPeriodInfo) {
          this.dom.forecastPeriodInfo.textContent = "Periodo: no disponible.";
        }
        if (this.dom.forecastSummary) {
          this.dom.forecastSummary.textContent =
            error?.payload?.error ||
            error?.message ||
            "No se pudo calcular el pronostico.";
        }
        if (this.dom.forecastKpiProducts) {
          this.dom.forecastKpiProducts.textContent = "0";
        }
        if (this.dom.forecastKpiActionable) {
          this.dom.forecastKpiActionable.textContent = "0";
        }
        if (this.dom.forecastKpiCritical) {
          this.dom.forecastKpiCritical.textContent = "0";
        }
        if (this.dom.forecastKpiCoverage) {
          this.dom.forecastKpiCoverage.textContent = "N/D";
        }
        if (this.dom.forecastResultCount) {
          this.dom.forecastResultCount.textContent = "Sin resultados";
        }
      } finally {
        this.clearTableSkeleton(this.dom.forecastTable);
        if (manageButton && this.dom.refreshForecastBtn) {
          this.setButtonBusy(this.dom.refreshForecastBtn, false);
        }
      }
    },

    renderDemandForecast(data) {
      if (!this.dom.forecastTable) {
        return;
      }
      const model = data?.model || {};
      const summary = data?.summary || {};
      const rows = Array.isArray(data?.forecast) ? data.forecast : [];
      const actionableRows = rows.filter((item) => {
        const suggested = Number(item?.suggested_purchase || 0);
        const risk = String(item?.risk_level || "").toLowerCase();
        return suggested > 0 || risk === "critico" || risk === "alerta";
      });
      const productsCount = Number(summary.products || rows.length || 0);
      const criticalCount = Number(summary.critical || 0);
      const avgCoverValue = Number(summary.avg_cover_days);
      const avgCoverText = Number.isFinite(avgCoverValue)
        ? `${this.formatDecimal(avgCoverValue, 1)} dias`
        : "N/D";
      const strategyLabel =
        model.strategy === "modelo_entrenado"
          ? "Modelo entrenado"
          : model.strategy === "regla_stock_minimo"
            ? "Regla de inventario"
            : "Heuristica";
      const quality = model.quality || "estimada";
      const confidence = Number(model.confidence || 0);
      const horizon = Number(
        model.horizon_days || data?.config?.horizon_days || 14,
      );
      const mape = model.mape;
      const fallbackAllTime = Boolean(data?.period?.fallback_all_time);
      const inventoryOnly = Boolean(data?.period?.inventory_only);
      const periodFrom = String(data?.period?.from || "").trim();
      const periodTo = String(data?.period?.to || "").trim();

      if (this.dom.forecastModelSummary) {
        this.dom.forecastModelSummary.textContent = "";
        this.dom.forecastModelSummary.classList.add("d-none");
      }

      if (this.dom.forecastModelBadges) {
        const badges = [
          {
            label: "Estrategia",
            value: strategyLabel,
            tone:
              model.strategy === "modelo_entrenado" ? "success" : "secondary",
          },
          { label: "Calidad", value: quality, tone: "primary" },
          {
            label: "Confianza",
            value: `${this.formatDecimal(confidence, 1)}%`,
            tone:
              confidence >= 70
                ? "success"
                : confidence >= 40
                  ? "warning"
                  : "danger",
          },
          {
            label: "MAPE",
            value: Number.isFinite(Number(mape))
              ? `${this.formatDecimal(mape, 1)}%`
              : "N/D",
            tone: "info",
          },
        ];
        this.dom.forecastModelBadges.innerHTML = badges
          .map(
            (entry) => `
          <span class="forecast-pill forecast-pill-${entry.tone}">
            <strong>${this.escape(entry.label)}:</strong> ${this.escape(entry.value)}
          </span>
        `,
          )
          .join("");
      }

      if (this.dom.forecastPeriodInfo) {
        let periodMessage = "Periodo analizado: histórico disponible.";
        if (periodFrom && periodTo) {
          periodMessage = `Periodo analizado: ${periodFrom} a ${periodTo}.`;
        }
        if (inventoryOnly) {
          periodMessage +=
            " No hubo ventas en el rango, se usó regla de inventario.";
        } else if (fallbackAllTime) {
          periodMessage +=
            " El rango no tuvo ventas, se usó histórico completo.";
        }
        this.dom.forecastPeriodInfo.textContent = periodMessage;
      }

      if (this.dom.forecastKpiProducts) {
        this.dom.forecastKpiProducts.textContent =
          this.formatNumber(productsCount);
      }
      if (this.dom.forecastKpiActionable) {
        this.dom.forecastKpiActionable.textContent = this.formatNumber(
          actionableRows.length,
        );
      }
      if (this.dom.forecastKpiCritical) {
        this.dom.forecastKpiCritical.textContent =
          this.formatNumber(criticalCount);
      }
      if (this.dom.forecastKpiCoverage) {
        this.dom.forecastKpiCoverage.textContent = avgCoverText;
      }

      if (this.dom.forecastSummary) {
        const chips = [
          {
            label: "Evaluados",
            value: this.formatNumber(productsCount),
            tone: "neutral",
          },
          {
            label: "Reponer ahora",
            value: this.formatNumber(actionableRows.length),
            tone: "primary",
          },
          {
            label: "Criticos",
            value: this.formatNumber(criticalCount),
            tone: "danger",
          },
          {
            label: "Alerta",
            value: this.formatNumber(summary.warning || 0),
            tone: "warning",
          },
          { label: "Cobertura prom.", value: avgCoverText, tone: "info" },
          {
            label: "Horizonte",
            value: `${this.formatNumber(horizon)} dias`,
            tone: "neutral",
          },
        ];
        this.dom.forecastSummary.innerHTML = chips
          .map(
            (chip) => `
          <span class="forecast-chip forecast-chip-${chip.tone}">
            <span class="label">${this.escape(chip.label)}</span>
            <strong>${this.escape(chip.value)}</strong>
          </span>
        `,
          )
          .join("");
      }

      if (!actionableRows.length) {
        if (this.dom.forecastResultCount) {
          this.dom.forecastResultCount.textContent = "0 resultados";
        }
        this.dom.forecastTable.innerHTML =
          '<tr><td colspan="5" class="text-center text-muted">No se detectan productos que requieran reposicion en este momento.</td></tr>';
        this.applyTableLabels(this.dom.forecastTable);
        return;
      }

      const searchTerm = (this.dom.forecastSearchInput?.value || "")
        .trim()
        .toLowerCase();
      const riskFilter = String(
        this.dom.forecastRiskFilter?.value || "all",
      ).toLowerCase();
      this.updateForecastQuickButtons(riskFilter);
      const sortBy = String(
        this.dom.forecastSortBy?.value || "risk_purchase",
      ).toLowerCase();
      const riskPriority = {
        critico: 0,
        alerta: 1,
        estable: 2,
        sin_dato: 3,
        "sin-dato": 3,
      };

      let visibleRows = actionableRows.filter((item) => {
        const productName = String(item.product || "").toLowerCase();
        const categoryName = String(item.category || "").toLowerCase();
        const riskValue = String(item.risk_level || "").toLowerCase();
        const searchOk =
          !searchTerm ||
          productName.includes(searchTerm) ||
          categoryName.includes(searchTerm);
        const normalizedRisk =
          riskValue === "sin-dato" ? "sin_dato" : riskValue;
        const riskOk = riskFilter === "all" || normalizedRisk === riskFilter;
        return searchOk && riskOk;
      });

      visibleRows.sort((a, b) => {
        const riskA =
          riskPriority[String(a.risk_level || "").toLowerCase()] ?? 9;
        const riskB =
          riskPriority[String(b.risk_level || "").toLowerCase()] ?? 9;
        const purchaseA = Number(a.suggested_purchase || 0);
        const purchaseB = Number(b.suggested_purchase || 0);
        const coverA = Number.isFinite(Number(a.cover_days))
          ? Number(a.cover_days)
          : Number.POSITIVE_INFINITY;
        const coverB = Number.isFinite(Number(b.cover_days))
          ? Number(b.cover_days)
          : Number.POSITIVE_INFINITY;
        const productA = String(a.product || "");
        const productB = String(b.product || "");

        if (sortBy === "purchase_desc") {
          return purchaseB - purchaseA || riskA - riskB || coverA - coverB;
        }
        if (sortBy === "cover_asc") {
          return coverA - coverB || riskA - riskB || purchaseB - purchaseA;
        }
        if (sortBy === "product_asc") {
          return (
            productA.localeCompare(productB, "es", { sensitivity: "base" }) ||
            riskA - riskB
          );
        }
        return riskA - riskB || purchaseB - purchaseA || coverA - coverB;
      });

      if (!visibleRows.length) {
        if (this.dom.forecastResultCount) {
          this.dom.forecastResultCount.textContent = "0 resultados";
        }
        this.dom.forecastTable.innerHTML =
          '<tr><td colspan="5" class="text-center text-muted">No hay resultados para el filtro aplicado.</td></tr>';
        this.applyTableLabels(this.dom.forecastTable);
        return;
      }

      if (this.dom.forecastResultCount) {
        this.dom.forecastResultCount.textContent = `${this.formatNumber(visibleRows.length)} resultados`;
      }

      this.dom.forecastTable.innerHTML = visibleRows
        .map((item) => {
          const predictedQty = Number(
            item.predicted_demand ?? item.predicted_qty ?? 0,
          );
          const predictedDaily = Number(
            item.daily_demand ?? item.predicted_daily ?? 0,
          );
          const risk = String(item.risk_level || "").toLowerCase();
          const riskClass =
            risk === "critico"
              ? "bg-danger"
              : risk === "alerta"
                ? "bg-warning text-dark"
                : risk === "estable"
                  ? "bg-success"
                  : "bg-secondary";
          const coverNumber = Number(item.cover_days);
          const hasCover = Number.isFinite(coverNumber);
          const cover = hasCover
            ? `${this.formatDecimal(coverNumber, 1)} dias`
            : "N/D";
          const coverPctRaw =
            hasCover && horizon > 0 ? (coverNumber / horizon) * 100 : 0;
          const coverPct = Math.max(0, Math.min(100, Math.round(coverPctRaw)));
          const coverTone =
            risk === "critico"
              ? "danger"
              : risk === "alerta"
                ? "warning"
                : "success";
          const runoutLabel = this.formatForecastRunoutLabel(item.runout_date);
          const runout = runoutLabel
            ? `<div class="text-muted small">${runoutLabel}</div>`
            : "";
          const riskLabel = risk
            ? `${risk.charAt(0).toUpperCase()}${risk.slice(1)}`
            : "Sin dato";
          const productName = String(item.product || "-");
          const imageUrl = this.resolveProductImageUrl({
            nombre: productName,
            imagen_url: item.imagen_url || item.image_url || item.image || "",
          });
          return `
          <tr>
            <td>
              <div class="product-cell-main">
                <img src="${imageUrl}" class="product-thumb-sm" alt="${this.escape(productName)}">
                <div>
                  <div class="fw-semibold">${this.escape(productName)}</div>
                  <div class="text-muted small">${this.escape(item.category || "Sin categoria")}</div>
                </div>
              </div>
            </td>
            <td class="text-end">
              <div class="fw-semibold">${this.formatDecimal(predictedQty, 2)} uds</div>
              <div class="text-muted small">${this.formatDecimal(predictedDaily, 2)} / dia</div>
            </td>
            <td>
              <div class="forecast-cover">
                <div class="d-flex justify-content-between align-items-center mb-1">
                  <span class="fw-semibold">${cover}</span>
                  <small class="text-muted">${coverPct}%</small>
                </div>
                <div class="forecast-cover-track">
                  <span class="forecast-cover-fill forecast-cover-${coverTone}" style="width:${coverPct}%"></span>
                </div>
              </div>
              ${runout}
            </td>
            <td><span class="badge ${riskClass}">${this.escape(riskLabel)}</span></td>
            <td class="text-end">
              <div class="fw-semibold fs-6">${this.formatNumber(item.suggested_purchase || 0)} uds</div>
              <div class="text-muted small">Compra sugerida</div>
            </td>
          </tr>
        `;
        })
        .join("");
      this.applyTableLabels(this.dom.forecastTable);
    },

    renderChart(key, canvas, config) {
      if (!window.Chart || !canvas) {
        return;
      }
      this.destroyChart(key);
      this.charts[key] = new Chart(canvas.getContext("2d"), config);
    },

    destroyChart(key) {
      if (this.charts[key]) {
        this.charts[key].destroy();
        delete this.charts[key];
      }
    },

    async loadSessions() {
      if (!this.can("sessions_manage")) {
        return;
      }
      if (this.dom.sessionsTable) {
        this.showTableSkeleton(this.dom.sessionsTable);
      }
      try {
        const data = await this.fetchJson("/api/sesiones");
        if (this.dom.sessionsSummaryBadge) {
          const summary = data.summary || {};
          this.dom.sessionsSummaryBadge.textContent = `Activas: ${this.formatNumber(summary.active || 0)} / Total: ${this.formatNumber(summary.total || 0)}`;
        }
        this.renderSessions(data.sessions || []);
      } catch (error) {
        console.error("No se pudieron cargar las sesiones", error);
        if (this.dom.sessionsTable) {
          this.clearTableSkeleton(this.dom.sessionsTable);
          this.dom.sessionsTable.innerHTML =
            '<tr><td colspan="8" class="text-center text-muted">No se pudieron cargar las sesiones.</td></tr>';
          this.applyTableLabels(this.dom.sessionsTable);
        }
      }
    },

    renderSessions(sessions) {
      if (!this.dom.sessionsTable) {
        return;
      }
      this.clearTableSkeleton(this.dom.sessionsTable);
      if (!sessions?.length) {
        this.dom.sessionsTable.innerHTML =
          '<tr><td colspan="8" class="text-center text-muted">Sin sesiones activas.</td></tr>';
        this.applyTableLabels(this.dom.sessionsTable);
        return;
      }
      const now = Date.now();
      this.dom.sessionsTable.innerHTML = sessions
        .map((session) => {
          const expires = session.expires_at
            ? new Date(session.expires_at).getTime()
            : null;
          const remaining = expires
            ? Math.max(0, Math.round((expires - now) / 1000))
            : null;
          const statusBadge =
            session.status === "active"
              ? '<span class="badge bg-success">Activa</span>'
              : session.status === "revoked"
                ? '<span class="badge bg-danger">Revocada</span>'
                : '<span class="badge bg-secondary">Expirada</span>';
          const disableRevoke = session.is_current ? "disabled" : "";
          return `
          <tr>
            <td>${this.escape(session.username || "-")}</td>
            <td class="text-uppercase">${this.escape(session.role || "-")}</td>
            <td>${this.escape(session.client || "-")}</td>
            <td>${this.formatDateTime(session.last_activity)}</td>
            <td>${this.formatDateTime(session.expires_at)}</td>
            <td>${remaining ? this.secondsToHms(remaining) : "--"}</td>
            <td>${statusBadge}</td>
            <td class="text-end">
              <button class="btn btn-sm btn-outline-danger" data-action="revoke" data-token="${this.escape(session.token || "")}" ${disableRevoke}>Revocar</button>
            </td>
          </tr>
        `;
        })
        .join("");
      this.applyTableLabels(this.dom.sessionsTable);
    },

    async revokeSession(token) {
      try {
        await this.fetchJson(`/api/sesiones/${encodeURIComponent(token)}`, {
          method: "DELETE",
        });
        this.loadSessions();
      } catch (error) {
        console.error("No se pudo revocar la sesion", error);
        window.alert("No se pudo revocar la sesion.");
      }
    },

    renderAccountInfo() {
      if (!this.state.user) {
        return;
      }
      if (this.dom.userProfileInfo) {
        this.dom.userProfileInfo.innerHTML = `
          <dl class="row mb-0">
            <dt class="col-sm-4 text-muted">Usuario</dt>
            <dd class="col-sm-8">${this.escape(this.state.user.username)}</dd>
            <dt class="col-sm-4 text-muted">Nombre</dt>
            <dd class="col-sm-8">${this.escape(this.state.user.name || "-")}</dd>
            <dt class="col-sm-4 text-muted">Ingreso</dt>
            <dd class="col-sm-8">${this.formatDateTime(this.state.user.login_at)}</dd>
            <dt class="col-sm-4 text-muted">Ultima actividad</dt>
            <dd class="col-sm-8">${this.formatDateTime(this.state.user.last_activity)}</dd>
          </dl>
        `;
      }
      if (this.dom.userRoleSummary) {
        const label =
          this.state.user.role_name || this.state.user.role || "Usuario";
        this.dom.userRoleSummary.textContent = `Rol: ${label}`;
      }
      if (this.dom.userRoleCapabilities) {
        const capabilities = [];
        if (this.can("dashboard_view")) {
          capabilities.push("Acceso al dashboard operativo.");
        }
        if (this.can("sales_create")) {
          capabilities.push("Registro y seguimiento de ventas.");
        } else if (this.can("sales_view")) {
          capabilities.push("Consulta de ventas.");
        }
        if (this.can("products_manage")) {
          capabilities.push("Gestion de productos e inventario.");
        } else if (this.can("products_view")) {
          capabilities.push("Consulta de catalogo e inventario.");
        }
        if (this.can("users_manage")) {
          capabilities.push("Administracion de usuarios y roles.");
        }
        if (this.can("audit_view")) {
          capabilities.push("Consulta de auditoria del sistema.");
        }
        if (this.can("backups_manage")) {
          capabilities.push("Gestion de respaldos del sistema.");
        }
        if (this.can("reports_view")) {
          capabilities.push("Acceso a reportes de ventas.");
        }
        if (this.can("statistics_view")) {
          capabilities.push("Acceso a estadisticas y pronostico IA.");
        }
        if (this.can("ai_chat")) {
          capabilities.push("Uso del asistente IA.");
        }
        if (!capabilities.length) {
          capabilities.push("Sin permisos funcionales configurados.");
        }
        this.dom.userRoleCapabilities.innerHTML = capabilities
          .map((item) => `<li>${this.escape(item)}</li>`)
          .join("");
      }
      if (this.dom.userSessionInfo) {
        const expires =
          this.state.sessionStatus?.expires_at ||
          this.state.user.session_expires_at;
        const idle = this.state.user.idle_minutes
          ? `${this.state.user.idle_minutes} min`
          : "No disponible";
        this.dom.userSessionInfo.innerHTML = `
          <p class="mb-1"><strong>Expira:</strong> ${expires ? this.formatDateTime(expires) : "No configurado"}</p>
          <p class="mb-0"><strong>Inactividad maxima:</strong> ${idle}</p>
        `;
      }
    },

    appendAiMessage(role, text) {
      if (!this.dom.aiChatConversation) {
        return;
      }
      const wrapper = document.createElement("div");
      wrapper.className = `ai-chat-message ${role === "assistant" ? "assistant" : "user"}`;
      const safeText = this.escape(text).replace(/\n/g, "<br>");
      wrapper.innerHTML = `
        <div class="bubble">
          <div class="role">${role === "assistant" ? "Asistente" : "Tu pregunta"}</div>
          <div>${safeText}</div>
        </div>
      `;
      this.dom.aiChatConversation.appendChild(wrapper);
      this.dom.aiChatConversation.scrollTop =
        this.dom.aiChatConversation.scrollHeight;
    },

    resetAiChatHistory() {
      if (this.dom.aiChatConversation) {
        this.dom.aiChatConversation.innerHTML = "";
      }
      if (this.dom.aiChatQuestion) {
        this.dom.aiChatQuestion.value = "";
      }
      if (this.dom.aiChatStatus) {
        this.dom.aiChatStatus.textContent = "Tip: usa Ctrl+Enter para enviar.";
      }
    },

    async handleAiChat() {
      if (!this.can("ai_chat")) {
        return;
      }
      const question = this.dom.aiChatQuestion?.value.trim();
      if (!question) {
        return;
      }
      this.appendAiMessage("user", question);
      if (this.dom.aiChatQuestion) {
        this.dom.aiChatQuestion.value = "";
      }
      if (this.dom.aiChatStatus) {
        this.dom.aiChatStatus.textContent = "Consultando...";
      }
      this.setButtonBusy(this.dom.aiChatSendBtn, true);
      try {
        const response = await this.fetchJson("/api/ia/chat", {
          method: "POST",
          body: { question },
        });
        let message = response.answer || "El asistente no devolvio respuesta.";
        this.appendAiMessage("assistant", message);
        if (this.dom.aiChatStatus) {
          this.dom.aiChatStatus.textContent = "Respuesta recibida.";
        }
      } catch (error) {
        const message =
          error?.payload?.error ||
          error?.message ||
          "No se pudo consultar al asistente.";
        this.appendAiMessage("assistant", message);
        if (this.dom.aiChatStatus) {
          this.dom.aiChatStatus.textContent = "Error al consultar.";
        }
      } finally {
        this.setButtonBusy(this.dom.aiChatSendBtn, false);
      }
    },
  });

  document.addEventListener("DOMContentLoaded", () => App.init());
})();
