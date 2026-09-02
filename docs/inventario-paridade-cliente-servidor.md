# Inventário de paridade cliente-servidor

- Estado: fronteira cliente-servidor vigente com contrato API `1.3.0`
- Data da revisão: 2026-09-02
- Runtime caracterizado: cliente Qt magro e servidor protegido como fonte principal
- Linha de base histórica: 618 testes aprovados; cobertura total 87,08%; Pytest em 128,11 s
- Gate E05: 856 testes aprovados; cobertura total 86,61%; Pytest em 178,00 s;
  `RESULTADO FINAL: APROVADO`
- Gate E06: 897 testes aprovados; cobertura total 86,88%; Pytest em 311,09 s;
  `RESULTADO FINAL: APROVADO`
- Gate E08: suíte obrigatória com 62 testes aprovados em 12,26 s; suíte completa com 955 testes
  aprovados em 137,33 s; mypy aprovado em 306 arquivos fonte; Ruff check aprovado e 15 arquivos
  Python alterados com formatação verificada.

## Finalidade e convenções

Este inventário liga cada ação visível atual ao método que a atende, à caracterização existente e ao
contrato de transporte esperado na arquitetura cliente-servidor. Ele também cobre os fluxos sem
controle visual atual que aparecem na matriz obrigatória de paridade, como fotos gerenciadas.

Os caminhos e nomes de DTO das tabelas de paridade foram estabilizados pela Etapa 1. A fonte
canônica revisável é `docs/api/openapi-v1.json`; o catálogo abaixo explicita método, rota, request,
response e códigos esperados. Todas as rotas, exceto `GET /health/live`, ficam sob `/api/v1` e
exigem Bearer.

Convenções das colunas:

- **Ação atual / método atual** identifica o slot Qt e o caso de uso ou helper chamado hoje;
- **Caracterização existente** aponta ao menos um teste pytest que comprova o fluxo;
- **Endpoint atual** descreve a fronteira vigente; `nenhum` significa estado puramente visual no
  cliente;
- **DTO esperado** é uma projeção de transporte sem comportamento de negócio. Nenhum DTO contém
  `Path`, entidade SQLAlchemy, agregado de domínio ou objeto PyMuPDF.

## Catálogo estabilizado da API v1

Convenções: `—` significa ausência de body; parâmetros de path/query e headers continuam descritos
na OpenAPI. Toda criação de job e todo upload exige `Idempotency-Key`. Os códigos comuns das rotas
protegidas são `401 AUTHENTICATION_FAILED`, `404 RESOURCE_NOT_FOUND`,
`409 OPERATION_CONFLICT`/`STALE_STATE`/`IDEMPOTENCY_CONFLICT`/`PROJECT_ALREADY_EXISTS`/
`INTEGRITY_ERROR`,
`413 UPLOAD_TOO_LARGE`,
`415 UNSUPPORTED_MEDIA_TYPE`, `422 VALIDATION_ERROR` e `500 INTERNAL_ERROR`.
`PDF_PASSWORD_REQUIRED` e `PDF_PASSWORD_INVALID` pertencem aos fluxos de upload/desbloqueio.

| Grupo | Método e rota v1 | Request | Response principal | HTTP/códigos esperados |
|---|---|---|---|---|
| saúde | `GET /health/live` | — | `HealthLiveResponse` | `200`; `500 INTERNAL_ERROR` |
| sessão | `GET /api/v1/session` | Bearer | `SessionCapabilitiesResponse` | `200`; códigos comuns |
| projetos | `GET /api/v1/projects` | paginação em query | `ProjectSummaryListResponse` | `200`; códigos comuns |
| projetos | `GET /api/v1/projects/by-service-note/{service_note}` | — | `ProjectDetailResponse` | `200`; `404 RESOURCE_NOT_FOUND`; `409 INTEGRITY_ERROR`; demais comuns |
| projetos | `POST /api/v1/projects` | `CreateProjectRequest` + idempotência | `ProjectDetailResponse` | `201`; códigos comuns |
| projetos | `GET /api/v1/projects/{project_id}` | — | `ProjectDetailResponse` | `200`; códigos comuns |
| projetos | `PATCH /api/v1/projects/{project_id}` | `UpdateProjectRequest` | `ProjectDetailResponse` | `200`; códigos comuns |
| projetos | `DELETE /api/v1/projects/{project_id}` | — | `DeleteProjectResponse` | `200`; códigos comuns |
| projetos | `GET /api/v1/projects/{project_id}/service-codes` | — | `ProjectServiceCodesResponse` | `200`; códigos comuns |
| projetos | `PUT /api/v1/projects/{project_id}/service-codes` | `ReplaceProjectServiceCodesRequest` | `ProjectServiceCodesResponse` | `200`; `409 STALE_STATE`; demais comuns |
| documentos | `POST /api/v1/projects/{project_id}/document-uploads` | multipart PDF + idempotência | `CreateUploadResponse` | `201`; comuns + `PDF_PASSWORD_REQUIRED` |
| documentos | `POST /api/v1/uploads/{upload_id}/unlock` | `UnlockPdfRequest` | `DocumentImportResultDto` | `200`; comuns + `PDF_PASSWORD_INVALID` |
| documentos | `PUT /api/v1/projects/{project_id}/page-order` | `ReplacePageOrderRequest` | `PageOrderResponse` | `200`; códigos comuns |
| documentos | `DELETE /api/v1/projects/{project_id}/documents/{document_id}` | — | `RemoveDocumentResponse` | `200`; códigos comuns |
| visualizador | `POST /api/v1/viewer-sessions` | multipart com um ou mais PDFs + idempotência | `CreateViewerSessionResponse` | `201`; comuns + códigos de PDF |
| visualizador | `DELETE /api/v1/viewer-sessions/{viewer_session_id}` | — | `CloseViewerSessionResponse` | `200`; códigos comuns |
| visualizador | `GET /api/v1/projects/{project_id}/viewer` | — | `ViewerProjectResponse` | `200`; códigos comuns |
| visualizador | `GET /api/v1/viewer-pages/{page_id}` | — | `ViewerPageDto` | `200`; códigos comuns |
| visualizador | `GET /api/v1/viewer-pages/{page_id}/preview` | DPI e rotação em query | `image/png` + headers de `RasterMetadataDto` | `200`; códigos comuns |
| visualizador | `GET /api/v1/viewer-pages/{page_id}/tiles` | clip normalizado, DPI e rotação em query | `image/png` + headers de `RasterMetadataDto` | `200`; códigos comuns |
| análise | `POST /api/v1/projects/{project_id}/analysis-jobs` | `CreateAnalysisJobRequest` + idempotência | `JobAcceptedResponse` | `202`; códigos comuns |
| jobs | `GET /api/v1/jobs/{job_id}` | — | `JobStatusResponse` | `200`; códigos comuns |
| jobs | `GET /api/v1/jobs/{job_id}/result` | — | `JobResultResponse` | `200`; `409 OPERATION_CONFLICT`; demais comuns |
| jobs | `POST /api/v1/jobs/{job_id}/cancel` | — | `CancelJobResponse` | `200`; `409 OPERATION_CONFLICT`; demais comuns |
| revisão | `GET /api/v1/review/projects` | paginação em query | `ReviewProjectSummaryListResponse` | `200`; códigos comuns |
| revisão | `GET /api/v1/projects/{project_id}/review-session` | — | `ReviewSessionResponse` | `200`; códigos comuns |
| revisão | `POST /api/v1/review/proposals/{proposal_id}/accept` | `AcceptReviewProposalRequest` | `ReviewDecisionResponse` | `200`; `409 STALE_STATE`; demais comuns |
| revisão | `POST /api/v1/review/proposals/{proposal_id}/reject` | `RejectReviewProposalRequest` | `ReviewDecisionResponse` | `200`; `409 STALE_STATE`; demais comuns |
| revisão | `POST /api/v1/projects/{project_id}/review/elements` | `CreateManualElementRequest` | `ReviewDecisionResponse` | `201`; `409 STALE_STATE`; demais comuns |
| revisão | `POST /api/v1/projects/{project_id}/review/relations` | `CreateManualRelationRequest` | `ReviewDecisionResponse` | `201`; `409 STALE_STATE`; demais comuns |
| documentação | `GET /api/v1/documentation/projects` | paginação em query | `ReviewProjectSummaryListResponse` | `200`; códigos comuns |
| documentação | `GET /api/v1/projects/{project_id}/documentation` | — | `DocumentationResponse` | `200`; códigos comuns |
| conformidade | `GET /api/v1/projects/{project_id}/compliance/latest` | — | `ComplianceExecutionResponse` | `200`; códigos comuns |
| conformidade | `GET /api/v1/projects/{project_id}/compliance/history` | paginação em query | `ComplianceHistoryResponse` | `200`; códigos comuns |
| conformidade | `POST /api/v1/projects/{project_id}/compliance-jobs` | `CreateComplianceJobRequest` + idempotência | `JobAcceptedResponse` | `202`; códigos comuns |
| GMAX | `GET /api/v1/projects/{project_id}/gmax` | — | `GmaxSummaryResponse` | `200`; `409 INTEGRITY_ERROR`; demais comuns |
| regras | `GET /api/v1/rules/active` | — | `ActiveRuleRegistryResponse` | `200`; códigos comuns |
| regras | `POST /api/v1/rules/import-preflights` | multipart JSON + idempotência | `RuleImportPreflightResponse` | `201`; `422 INTEGRITY_ERROR`; demais comuns |
| regras | `POST /api/v1/rules/imports` | `ConfirmRuleImportRequest` | `RuleImportResponse` | `201`; `409 STALE_STATE`; demais comuns |
| regras | `GET /api/v1/rules/active/download` | — | stream JSON | `200`; códigos comuns |
| portabilidade | `POST /api/v1/projects/{project_id}/export-jobs` | `CreateExportJobRequest` + idempotência | `JobAcceptedResponse` | `202`; códigos comuns |
| portabilidade | `POST /api/v1/project-import-preflights` | multipart `.zphproj` + idempotência | `ProjectImportPreflightResponse` | `201`; `422 INTEGRITY_ERROR`; demais comuns |
| portabilidade | `POST /api/v1/project-import-jobs` | `ConfirmProjectImportRequest` + idempotência | `JobAcceptedResponse` | `202`; `409 STALE_STATE`; demais comuns |
| backup | `POST /api/v1/backup-preflights` | — | `BackupPreflightResponse` | `201`; códigos comuns |
| backup | `POST /api/v1/backup-jobs` | `CreateBackupJobRequest` + idempotência | `JobAcceptedResponse` | `202`; `409 STALE_STATE`; demais comuns |
| backup | `POST /api/v1/backup-restore-preflights` | multipart `.zphbackup` + idempotência | `BackupRestorePreflightResponse` | `201`; `422 INTEGRITY_ERROR`; demais comuns |
| backup | `POST /api/v1/backup-restore-jobs` | `ConfirmBackupRestoreRequest` + idempotência | `JobAcceptedResponse` | `202`; `409 STALE_STATE`; demais comuns |
| transferências | `GET /api/v1/downloads/{download_id}` | — | stream binário + headers de integridade | `200`; códigos comuns |
| transferências | `GET /api/v1/downloads/{download_id}/metadata` | — | `DownloadMetadataDto` | `200`; códigos comuns |
| fotos | `GET /api/v1/projects/{project_id}/photos` | — | `ManagedPhotoListResponse` | `200`; códigos comuns |
| fotos | `POST /api/v1/projects/{project_id}/elements/{element_id}/photos` | multipart imagem + idempotência | `ManagedPhotoResponse` | `201`; códigos comuns |
| fotos | `DELETE /api/v1/projects/{project_id}/elements/{element_id}/photos/{photo_id}` | — | `RemoveManagedPhotoResponse` | `200`; códigos comuns |
| fotos | `GET /api/v1/projects/{project_id}/photos/{photo_id}/content` | — | stream do MIME validado | `200`; códigos comuns |

## Painel Projeto

| Ação visível atual | Método atual | Caracterização existente | Endpoint remoto | DTO esperado |
|---|---|---|---|---|
| listar, pesquisar e selecionar projeto | `ProjectPanelWidget.atualizar_projetos` / combo editável sem inserção | `tests/e2e/test_mvp_ui.py::test_project_combo_searches_only_digits_without_inserting_or_losing_ids` | `GET /api/v1/projects`; resolução exata em `GET /api/v1/projects/by-service-note/{service_note}` | `ProjectSummaryListResponse`; `ProjectDetailResponse` |
| criar projeto por NS ou abrir o existente | `ProjectPanelWidget.criar_projeto` / `_offer_open_existing` → `ProjectGateway` | `tests/e2e/test_mvp_ui.py::test_project_open_create_dialogs_and_refusals_return_to_initial_state`; `::test_project_creation_race_reuses_existing_dialog_without_repeating_post` | `GET /api/v1/projects/by-service-note/{service_note}` e `POST /api/v1/projects` | `CreateProjectRequest` → `ProjectDetailResponse`; `409 PROJECT_ALREADY_EXISTS` contém somente ID/NS |
| abrir/detalhar projeto ou criar NS ausente | `ProjectPanelWidget.abrir_selecionado` / `_offer_create_missing` → `ProjectGateway` | `tests/e2e/test_mvp_ui.py::test_project_open_create_dialogs_and_refusals_return_to_initial_state` | resolução exata e `GET /api/v1/projects/{project_id}`; criação única quando confirmada | `ProjectDetailResponse` |
| alterar NS | `ProjectPanelWidget.alterar_numero_ns` → `ProjectGateway.update_project` | `tests/server/test_project_document_api.py::test_project_service_note_conflict_replay_rename_and_safe_details` | `PATCH /api/v1/projects/{project_id}` | `UpdateProjectRequest` → `ProjectDetailResponse`; `409 PROJECT_ALREADY_EXISTS` |
| cadastrar/remover códigos de serviço | `_add_service_code` / `_remove_selected_service_codes` → `ProjectGateway.get_service_codes` / `replace_service_codes` | `tests/e2e/test_mvp_ui.py::test_project_service_codes_ui_is_remote_canonical_accessible_and_conflict_safe`; `::test_environmental_actions_full_client_matrix_uses_current_service_codes` | `GET`/`PUT /api/v1/projects/{project_id}/service-codes` | `ProjectServiceCodesResponse`; `ReplaceProjectServiceCodesRequest`; `409 STALE_STATE` recarrega a coleção vigente |
| excluir projeto após confirmação | `ProjectPanelWidget.excluir_projeto` → `ServicoFluxoMvp.excluir_projeto` | `tests/integration/test_mvp_workflow.py::test_delete_project_with_confirmed_review_removes_dependents_in_safe_order` | `DELETE /api/v1/projects/{project_id}` | `DeleteProjectResponse` com contagens de limpeza |
| selecionar e adicionar vários PDFs | `ProjectPanelWidget.selecionar_pdfs` / `_importar_selecao` → `ServicoFluxoMvp.importar_pdfs` | `tests/integration/test_mvp_workflow.py::test_multiple_pdf_import_is_atomic_and_preserves_order` | `POST /api/v1/projects/{project_id}/document-uploads` | multipart + `CreateUploadResponse`/`DocumentImportResultDto`; `Idempotency-Key` |
| informar senha de cada PDF, repetir até três vezes ou pular o arquivo | `ResolvedorCredenciaisPdf.executar` / `ProjectPanelWidget._acao_importacao_pdf` | `tests/integration/test_protected_pdf_ui.py::test_wrong_password_limit_and_cancel_produce_partial_import_summary` | `POST /api/v1/uploads/{upload_id}/unlock` | `UnlockPdfRequest` → `DocumentImportResultDto` ou erro `PDF_PASSWORD_*` |
| arrastar folha, subir ou descer e persistir ordem | `_move_selected_page`, `_page_order_changed`, `_persist_page_order` → `ServicoFluxoMvp.reordenar_paginas` | `tests/e2e/test_mvp_ui.py::test_user_can_reorder_project_pdfs_and_reopen_in_reading_order` | `PUT /api/v1/projects/{project_id}/page-order` | `ReplacePageOrderRequest` → `PageOrderResponse` |
| remover PDFs das folhas selecionadas | `ProjectPanelWidget.remover_pdfs` → `ServicoFluxoMvp.remover_documentos` | `tests/integration/test_mvp_workflow.py::test_remove_pdf_prunes_only_dependent_data_and_project_can_be_deleted` | `DELETE /api/v1/projects/{project_id}/documents/{document_id}` | `RemoveDocumentResponse` |
| iniciar análise completa | `ProjectPanelWidget.executar_analise` / `_PipelineWorker.run` → `ServicoFluxoMvp.executar_pipeline` | `tests/e2e/test_mvp_ui.py::test_user_can_create_import_analyze_review_and_reopen_from_ui` | `POST /api/v1/projects/{project_id}/analysis-jobs` | `CreateAnalysisJobRequest` → `JobAcceptedResponse` (202) |
| acompanhar progresso e cancelar análise | `_update_progress`, `cancelar_analise` e token `Event` | `tests/integration/test_mvp_workflow.py::test_cancel_and_resume_pipeline_reuses_completed_work_without_duplicates` | `GET /api/v1/jobs/{job_id}` e `POST /api/v1/jobs/{job_id}/cancel` | `JobStatusResponse`, `CancelJobResponse` |
| abrir “Como usar” | `ProjectPanelWidget.exibir_guia_aceite` | `tests/integration/test_window.py::test_main_window_smoke` | nenhum; conteúdo estático do cliente | nenhum DTO de negócio |

## Visualizador de PDF

| Ação visível atual | Método atual | Caracterização existente | Endpoint atual | DTO esperado |
|---|---|---|---|---|
| abrir um ou mais PDFs avulsos | `PdfViewerWidget.selecionar_pdf` / `carregar_pdf` | `tests/integration/test_window.py::test_pdf_viewer_opens_selected_files_as_one_ordered_project` | `POST /api/v1/viewer-sessions` e upload(s) da sessão | `CreateViewerSessionResponse`, `ViewerDocumentDto` |
| abrir folhas do projeto na ordem persistida | `PdfViewerWidget.carregar_projeto` / `_ordered_project_pages` | `tests/integration/test_window.py::test_pdf_viewer_follows_page_order_across_different_files` | `GET /api/v1/projects/{project_id}/viewer` | `ViewerProjectResponse` com `ViewerPageDto` |
| anterior, próxima e número da folha | `_change_page`, `ir_para_folha`, `_render_current_page` | `tests/integration/test_window.py::test_pdf_viewer_navigation_zoom_rotation_and_overlays` | `GET /api/v1/viewer-pages/{page_id}` | `ViewerPageDto` |
| reduzir, ampliar e ajustar à página | `_zoom_out`, `_zoom_in`, `_fit_page`; `PdfGraphicsView.definir_zoom` | `tests/integration/test_window.py::test_pdf_viewer_navigation_zoom_rotation_and_overlays` | nenhum para o estado visual; raster usa as rotas abaixo | `ViewportState` local, não transportado como regra de negócio |
| girar a visualização 90° | `_rotate_page` | `tests/integration/test_pdf_viewer_progressive.py::test_rotated_overlays_remain_aligned_and_review_link_is_clickable` | parâmetro de leitura em `GET /api/v1/viewer-pages/{page_id}/preview` e `/tiles` | `RasterRequestParams`/headers de raster |
| receber prévia e tiles conforme viewport | `_request_raster`, `_schedule_viewport_tiles`, `FilaRenderizacao` e `CacheLruBytes` | `tests/integration/test_pdf_viewer_progressive.py::test_rendering_is_responsive_and_never_rasterizes_on_ui_thread` | `GET /api/v1/viewer-pages/{page_id}/preview` e `GET /api/v1/viewer-pages/{page_id}/tiles` | `image/png` + `RasterMetadataDto` |
| descartar resultado obsoleto ao trocar página/zoom/origem | `_request_is_current`, `_cancel_current_rendering` | `tests/integration/test_pdf_viewer_progressive.py::test_old_page_result_is_discarded_after_out_of_order_navigation` | cancelamento/abandono de request de leitura; sem mutação | `generation` local e `RasterMetadataDto` correlacionável |
| clicar em overlay de revisão ou callout | `PdfGraphicsView.definir_propostas_revisao`, `selecionar_proposta`, `selecionar_callout` | `tests/integration/test_compliance_callout_viewer.py::test_callout_layer_draws_box_text_open_arrows_and_coexists_with_review_links` | overlays vêm nas projeções de revisão/conformidade | `ReviewOverlayDto`, `ComplianceCalloutDto` |
| arrastar caixa de callout na sessão aberta | `CalloutBoxItem.itemChange` / `PdfViewerWidget._callout_moved` | `tests/integration/test_compliance_callout_viewer.py::test_callout_box_drag_keeps_anchor_fixed_updates_arrow_and_preserves_position` | nenhum para posição visual efêmera nesta versão | `CalloutVisualState` local |
| fechar/limpar sessão avulsa | `PdfViewerWidget.limpar`, `encerrar`, `_close_sessions` | `tests/integration/test_pdf_viewer_progressive.py::test_closing_stops_render_thread_and_closes_verified_sessions` | `DELETE /api/v1/viewer-sessions/{viewer_session_id}` | `CloseViewerSessionResponse` |

## Painel Resultados e revisão humana

| Ação visível atual | Método atual | Caracterização existente | Endpoint atual | DTO esperado |
|---|---|---|---|---|
| atualizar lista e abrir projeto analisado | `ReviewPanelWidget.atualizar_projetos` / `abrir_projeto` → `ServicoRevisaoHumana.listar_projetos` / `carregar_sessao` | `tests/integration/test_review_panel.py::test_results_panel_groups_relationships_and_links_elements_to_pdf` | `GET /api/v1/review/projects` e `GET /api/v1/projects/{project_id}/review-session` | `ReviewProjectSummaryListResponse`, `ReviewSessionResponse` |
| filtrar localmente por classe, estado de revisão e situação da obra | `_refresh_proposals` / `_filtered_items` | `tests/integration/test_review_panel.py::test_results_panel_groups_relationships_and_links_elements_to_pdf` | nenhum; filtro sobre a projeção carregada | campos fechados `category`, `review_state` e `situation` em `ReviewProposalDto`; `CHANGE` é apresentado como `A alterar` |
| ver regiões, elementos e relações | `_populate_result_tree` e `_region_label` | `tests/integration/test_review_panel.py::test_results_panel_groups_relationships_and_links_elements_to_pdf` | `GET /api/v1/projects/{project_id}/review-session` | `AnalysisRegionDto`, `ReviewProposalDto`, `ReviewRelationDto` |
| ver vãos, tipo topológico, endpoints e origem do comprimento | `_refresh_spans` | `tests/integration/test_review_panel.py::test_results_panel_has_span_tab_with_situation_cable_and_length_source`; `tests/server/test_review_api.py::test_span_projection_exposes_type_change_and_delivery_endpoint` | mesma sessão de revisão | `DetectedSpanDto` com `SpanType`, rótulo do tipo, IDs dos pontos e rótulos de endpoint calculados pelo servidor |
| selecionar item e navegar até evidência no PDF | `_select_tree_proposal`, `_select_span`, `_select_proposal_id` | `tests/integration/test_review_panel.py::test_results_panel_groups_relationships_and_links_elements_to_pdf` | metadados de navegação na sessão; raster pelo visualizador | `EvidenceNavigationDto` |
| mostrar/ocultar região, elemento ou vão | `_set_region_visible`, `_set_element_visible`, `_set_span_visible` | `tests/integration/test_review_panel.py::test_result_visibility_can_hide_a_whole_point_or_one_element` | nenhum; visibilidade é estado visual local | IDs e geometrias normalizadas nos DTOs de revisão; overlays carregam `situation=CHANGE` e `situation_label=A alterar` sem derivação local |
| aceitar ou ajustar elemento/relação | `aceitar_selecionada` → `confirmar_elemento` / `confirmar_relacao` | `tests/integration/test_human_review.py::test_accept_adjust_reject_and_reopen_preserve_immutable_history` | `POST /api/v1/review/proposals/{proposal_id}/accept` | `AcceptReviewProposalRequest` → `ReviewDecisionResponse` |
| rejeitar proposta | `rejeitar_selecionada` → `ServicoRevisaoHumana.rejeitar` | `tests/integration/test_human_review.py::test_accept_adjust_reject_and_reopen_preserve_immutable_history` | `POST /api/v1/review/proposals/{proposal_id}/reject` | `RejectReviewProposalRequest` → `ReviewDecisionResponse` |
| criar elemento manual | `criar_elemento_manual` → `ServicoRevisaoHumana.criar_elemento_manual` | `tests/integration/test_human_review.py::test_confirm_relation_and_manual_creations_are_persisted_with_author` | `POST /api/v1/projects/{project_id}/review/elements` | `CreateManualElementRequest` → `ReviewDecisionResponse` |
| criar relação manual | `criar_relacao_manual` → `ServicoRevisaoHumana.criar_relacao_manual` | `tests/integration/test_human_review.py::test_confirm_relation_and_manual_creations_are_persisted_with_author` | `POST /api/v1/projects/{project_id}/review/relations` | `CreateManualRelationRequest` → `ReviewDecisionResponse` |
| alternar quebra de linha das tabelas | `TableWordWrapController` nos elementos e vãos | `tests/integration/test_review_panel.py::test_review_tables_toggle_word_wrap_and_keep_interactions_after_reload` | nenhum | estado visual local |

## Painel Documentação, conformidade e regras

| Ação visível atual | Método atual | Caracterização existente | Endpoint remoto | DTO esperado |
|---|---|---|---|---|
| selecionar projeto analisado | `DocumentationPanelWidget.abrir_projeto` → `DocumentationGateway` | `tests/integration/test_review_panel.py::test_documentation_panel_has_own_document_and_compliance_views` | `GET /api/v1/documentation/projects` e `GET /api/v1/projects/{project_id}/documentation` | `ReviewProjectSummaryListResponse`, `DocumentationResponse` com `DocumentFieldDto` |
| ver campos documentais e navegar à evidência | `_populate_documents`, `_navigate_document_item` | `tests/integration/test_review_panel.py::test_documentation_panel_has_own_document_and_compliance_views` | mesma rota de documentação | `DocumentFieldDto`, `EvidenceNavigationDto` |
| carregar a última conformidade e indicar resultado desatualizado | `_load_persisted_result` → `DocumentationGateway.get_latest_compliance` | `tests/integration/test_compliance_analysis.py::test_panel_loads_latest_marks_stale_and_reapplies_without_ocr` | `GET /api/v1/projects/{project_id}/compliance/latest` | `ComplianceExecutionResponse` |
| consultar histórico auditável | sem controle dedicado hoje; `ExecutarAnaliseConformidade.listar_historico` já existe | `tests/integration/test_compliance_analysis.py::test_execution_is_deterministic_preserves_history_and_survives_restart` | `GET /api/v1/projects/{project_id}/compliance/history` | `ComplianceHistoryResponse` |
| analisar conformidade explicitamente | `_analyze_current_compliance` → criação/polling do job remoto | `tests/integration/test_compliance_analysis.py::test_panel_loads_latest_marks_stale_and_reapplies_without_ocr` | `POST /api/v1/projects/{project_id}/compliance-jobs` | `CreateComplianceJobRequest` → `JobAcceptedResponse` |
| avaliar impacto/servidão contra ações concluídas | mesmo job remoto; cliente apresenta os DTOs e callouts compilados | `tests/e2e/test_mvp_ui.py::test_environmental_actions_full_client_matrix_uses_current_service_codes`; `tests/integration/test_project_http_gateway.py::test_two_http_clients_run_full_project_flow_and_survive_server_restart` | mesmo endpoint de job; consultas SQL permanecem internas ao servidor | `ComplianceExecutionResponse` com títulos exatos, `ComplianceFindingDto`, `ComplianceCalloutDto` e navegação por evidência |
| selecionar achado e navegar ao alvo/callout | `_navigate_finding_item`, `_select_finding_id` | `tests/integration/test_compliance_callout_viewer.py::test_multipage_callout_visual_qa_captures_show_hide_and_correct_page` | achados e callouts na resposta de conformidade | `ComplianceFindingDto`, `ComplianceCalloutDto` |
| exibir/ocultar um ou todos os callouts | `_set_finding_visible`, `_set_all_findings_visible` | `tests/integration/test_compliance_visibility.py::test_hidden_state_survives_navigation_and_resets_for_project_or_execution` | nenhum; visibilidade e posição manual são locais | IDs de callout na projeção; estado visual local |
| ver revisão ativa, números, estado e detalhes das regras | `atualizar_regras`, `_populate_rules`, `_show_rule_details` → `DocumentationGateway` | `tests/integration/test_compliance_rules_panel.py::test_rule_ids_stay_internal_and_details_use_the_fact_catalog` | `GET /api/v1/rules/active` | `ActiveRuleRegistryResponse`, `RuleSummaryDto`, `RuleDetailDto` |
| importar JSON com preflight e confirmação | `_import_registry` → upload e confirmação pelo gateway | `tests/integration/test_compliance_rules_panel.py::test_rules_view_only_imports_exports_and_survives_restart` | `POST /api/v1/rules/import-preflights` e `POST /api/v1/rules/imports` | upload + `RuleImportPreflightResponse`; `ConfirmRuleImportRequest` |
| exportar revisão ativa | `_export_registry` → download autenticado pelo gateway | `tests/integration/test_compliance_rules_panel.py::test_rules_view_only_imports_exports_and_survives_restart` | `GET /api/v1/rules/active/download` | bytes JSON com integridade HTTP |
| alternar quebra de linha nas três abas | `TableWordWrapController` | `tests/integration/test_review_panel.py::test_documentation_tables_toggle_word_wrap_and_recalculate_after_reload` | nenhum | estado visual local |

## Painel GMAX

| Ação visível atual | Método atual | Caracterização existente | Endpoint atual | DTO esperado |
|---|---|---|---|---|
| abrir ou atualizar o resumo somente leitura | `GmaxPanelWidget.abrir_projeto` / `atualizar` → `DocumentationGateway.get_gmax` | `tests/integration/test_gmax_panel.py::test_gmax_panel_is_read_only_accessible_and_maps_current_select_results`; `tests/integration/test_compliance_analysis.py::test_gmax_projects_market_and_executed_rows_without_new_external_io` | `GET /api/v1/projects/{project_id}/gmax` | `GmaxSummaryResponse` com mercado e dois `GmaxCheckDto` canônicos |
| distinguir sem execução, sem gatilho, sem serviços, stale e bloqueio de NS | projeção servidor + textos fechados do `GmaxPanelWidget` | `tests/integration/test_compliance_analysis.py::test_gmax_distinguishes_missing_triggers_from_missing_service_codes`; `::test_gmax_prioritizes_current_ns_block_and_hides_previous_results`; `tests/integration/test_gmax_panel.py::test_gmax_panel_distinguishes_non_current_states_without_color` | mesmo GET; nenhuma operação de escrita ou consulta SQL | `GmaxSnapshotState`, `GmaxQueryState`, `row_found: bool | null` |
| sincronizar abertura, limpeza e término da conformidade | sinais `project_opened`, `project_cleared` e `compliance_finished` | `tests/e2e/test_mvp_ui.py::test_project_open_create_dialogs_and_refusals_return_to_initial_state`; `tests/integration/test_gmax_panel.py::test_documentation_panel_emits_project_and_terminal_status_for_gmax_refresh` | mesmo GET apenas para o projeto ativo | `GmaxSummaryResponse` |

## Painel Exportar e fotos

| Ação visível atual | Método atual | Caracterização existente | Endpoint atual | DTO esperado |
|---|---|---|---|---|
| selecionar projeto para exportação | `PortabilityPanelWidget.atualizar_projetos` → `PortabilityGateway.list_projects` | `tests/integration/test_portability_panel.py::test_panel_exposes_only_user_deliverables` | `GET /api/v1/projects` | `ProjectSummaryListResponse` |
| baixar PDF com anotações | `_export(ANNOTATED_PDF)` → criação e download autenticado | `tests/server/test_deliverable_exports.py::test_pdf_callout_is_a_downloadable_annotation_even_on_rotated_page` | `POST /api/v1/projects/{project_id}/deliverable-exports` e `GET /api/v1/downloads/{download_id}` | `CreateDeliverableExportRequest`, `DownloadMetadataDto` |
| baixar Resultados | `_export(RESULTS_XLSX)` → planilhas Elementos e Vãos; Vãos inclui **Tipo** e endpoints como pontos | `tests/server/test_deliverable_exports.py::test_server_generates_pdf_and_three_real_xlsx_deliverables`; `::test_results_span_sheet_presents_the_public_review_contract` | mesmos endpoints de criação/download | `CreateDeliverableExportRequest`, `DownloadMetadataDto`; linhas compiladas do mesmo `DetectedSpanDto` usado pelo painel |
| baixar Documentação | `_export(DOCUMENTATION_XLSX)` → planilha Documentação | mesmo teste de entregáveis reais | mesmos endpoints de criação/download | `CreateDeliverableExportRequest`, `DownloadMetadataDto` |
| baixar Conformidade | `_export(COMPLIANCE_XLSX)` → planilhas Conformidade e Regras | mesmo teste de entregáveis reais | mesmos endpoints de criação/download | `CreateDeliverableExportRequest`, `DownloadMetadataDto` |
| acompanhar e cancelar download | `_show_progress`, `cancelar_operacao`, `_DeliverableExportWorker` | `tests/integration/test_portability_panel.py::test_each_action_downloads_the_server_compiled_file` | download autenticado e cancelamento local antes da publicação | `DownloadMetadataDto` |
| listar fotos de elementos | sem controle visual atual; API servidor | `tests/server/test_project_document_api.py` | `GET /api/v1/projects/{project_id}/photos` | `ManagedPhotoListResponse` |
| anexar/localizar foto | sem controle visual atual; API servidor | `tests/server/test_project_document_api.py` | `POST /api/v1/projects/{project_id}/elements/{element_id}/photos` | multipart + `ManagedPhotoResponse` |
| remover foto | sem controle visual atual; API servidor | `tests/server/test_project_document_api.py` | `DELETE /api/v1/projects/{project_id}/elements/{element_id}/photos/{photo_id}` | `RemoveManagedPhotoResponse` |
| baixar foto | sem controle visual e sem ação pública dedicada hoje; conteúdo participa de portabilidade/backup | testes do servidor e round trip comprovam hash e associação | `GET /api/v1/projects/{project_id}/photos/{photo_id}/content` | stream do MIME validado + `DownloadMetadataDto` |

## Janela, preferências locais, sessão e coordenação

| Ação visível atual | Método atual | Caracterização existente | Endpoint atual | DTO esperado |
|---|---|---|---|---|
| alternar tema claro/escuro | `MainWindow._select_light_theme`, `_select_dark_theme`, `_select_theme` → `QSettings` | `tests/integration/test_window.py::test_theme_menu_switches_immediately_and_is_restored_before_window_is_shown` | nenhum | `ui-state.ini` local |
| mover, desacoplar, reacoplar, maximizar, minimizar, fechar e reabrir painéis | `_DockTitleBar` e `MainWindow._register_dock` | `tests/integration/test_window.py::test_floating_panel_has_window_controls_and_can_be_reopened` | nenhum | geometria/estado de docks local |
| restaurar tema, geometria, docks e última folha | bootstrap/MainWindow/ProjectPanel com `QSettings` | `tests/integration/test_window.py::test_theme_switch_preserves_project_pdf_callout_zoom_selection_and_wrap_toggles` | nenhum | `ui-state.ini` local; senha nunca incluída |
| consultar orientação de OCR indisponível | `MainWindow._show_startup_ocr_diagnostic` | `tests/integration/test_window.py::test_startup_exposes_actionable_portuguese_ocr_remediation` | diagnóstico protegido em `GET /api/v1/session` | `SessionCapabilitiesResponse` com diagnóstico seguro |
| observar conflito global e bloqueio de ações | `_OperationStateBridge`, `set_global_operation`, `CoordenadorOperacoes.adquirir` | `tests/unit/test_operation_coordinator.py::test_conflict_and_reentry_are_refused_immediately_with_friendly_message` | HTTP 409 e estado global nos jobs | `ErrorEnvelope` (`OPERATION_CONFLICT`) e `GlobalOperationDto` |
| conectar por URL e senha | `ConnectionDialog._connect` → `ConnectionManager.connect` | `tests/unit/test_client_connection.py::test_connection_dialog_rejects_wrong_password_then_accepts_retry`; `tests/integration/test_client_reconnection.py::test_client_opens_authenticated_blocks_on_disconnect_and_reconnects` | `GET /api/v1/session`; `GET /health/live` público | `SessionCapabilitiesResponse`; erro `AUTHENTICATION_FAILED` |

## Cobertura explícita da matriz de paridade do roadmap

Na Etapa 11, todas as linhas abaixo também foram reexecutadas pela fronteira distribuída em
`scripts/stage11_parity_gate.py`: ZIP PyInstaller e wheel do cliente isolado, imagem Docker do
servidor sem bind mount, restart e auditoria do tráfego. A prova final não substitui os testes de
comportamento listados; ela confirma que a mesma cobertura permanece válida após a separação.

| Item obrigatório da matriz | Linhas deste inventário | Prova atual mínima |
|---|---|---|
| pesquisar NS, tratar existente/ausente e corrida de criação | Painel Projeto, linhas 1–3 | `tests/e2e/test_mvp_ui.py::test_project_combo_searches_only_digits_without_inserting_or_losing_ids`; `::test_project_open_create_dialogs_and_refusals_return_to_initial_state`; `::test_project_creation_race_reuses_existing_dialog_without_repeating_post`; `tests/server/test_project_document_api.py::test_two_concurrent_project_creations_publish_only_one_service_note` |
| criar/abrir/alterar NS/serviços/excluir projeto | Painel Projeto, linhas 1–6 | `tests/integration/test_mvp_workflow.py::test_project_identifier_is_a_user_supplied_ten_digit_service_note`; `tests/e2e/test_mvp_ui.py::test_environmental_actions_full_client_matrix_uses_current_service_codes`; `::test_project_service_codes_ui_is_remote_canonical_accessible_and_conflict_safe` |
| selecionar e importar múltiplos PDFs | Painel Projeto, linha 7 | `tests/integration/test_mvp_workflow.py::test_multiple_pdf_import_is_atomic_and_preserves_order` |
| senha de PDF, três tentativas e descarte seguro | Painel Projeto, linha 8 | `tests/integration/test_protected_pdf_ui.py::test_distinct_passwords_are_reused_in_session_and_never_leak_to_artifacts`; `::test_wrong_password_limit_and_cancel_produce_partial_import_summary` |
| reordenar páginas e remover documentos | Painel Projeto, linhas 9–10 | `tests/e2e/test_mvp_ui.py::test_user_can_reorder_project_pdfs_and_reopen_in_reading_order`; `tests/integration/test_mvp_workflow.py::test_remove_pdf_prunes_only_dependent_data_and_project_can_be_deleted` |
| PDF avulso no visualizador | Visualizador, linhas 1 e 10 | `tests/integration/test_window.py::test_pdf_viewer_opens_selected_files_as_one_ordered_project`; `tests/integration/test_pdf_viewer_progressive.py::test_closing_stops_render_thread_and_closes_verified_sessions` |
| zoom, rotação, prévia, tiles e paginação | Visualizador, linhas 3–7 | `tests/integration/test_window.py::test_pdf_viewer_navigation_zoom_rotation_and_overlays`; `tests/integration/test_pdf_viewer_progressive.py::test_old_page_result_is_discarded_after_out_of_order_navigation` |
| análise, OCR, interpretação e promoção | Painel Projeto, linha 11 | `tests/e2e/test_mvp_ui.py::test_user_can_create_import_analyze_review_and_reopen_from_ui`; `tests/integration/test_interpretation_pipeline.py::test_pipeline_persists_cross_run_provenance_and_reuses_completed_result` |
| regiões, elementos, relações e vãos | Resultados, linhas 3–4 | `tests/integration/test_review_panel.py::test_results_panel_groups_relationships_and_links_elements_to_pdf`; `::test_results_panel_has_span_tab_with_situation_cable_and_length_source` |
| revisão humana e criações manuais | Resultados, linhas 7–10 | `tests/integration/test_human_review.py::test_accept_adjust_reject_and_reopen_preserve_immutable_history`; `::test_confirm_relation_and_manual_creations_are_persisted_with_author` |
| documentação, conformidade e callouts | Documentação, linhas 1–8 | `tests/e2e/test_mvp_ui.py::test_environmental_actions_full_client_matrix_uses_current_service_codes`; `tests/integration/test_compliance_analysis.py::test_panel_loads_latest_marks_stale_and_reapplies_without_ocr`; `tests/integration/test_compliance_callout_viewer.py::test_callout_anchor_survives_zoom_resize_rotation_tiles_and_page_changes` |
| GMAX rural/urbano, SELECT executado/não executado e bloqueio pré-SQL | Painel GMAX, linhas 1–3 | `tests/integration/test_compliance_analysis.py::test_gmax_projects_market_and_executed_rows_without_new_external_io`; `::test_gmax_distinguishes_missing_triggers_from_missing_service_codes`; `::test_gmax_prioritizes_current_ns_block_and_hides_previous_results`; `tests/e2e/test_mvp_ui.py::test_environmental_actions_full_client_matrix_uses_current_service_codes` |
| importar/exportar regras | Documentação, linhas 8–10 | `tests/integration/test_compliance_rules_panel.py::test_rules_view_only_imports_exports_and_survives_restart`; `tests/unit/test_compliance_catalog_parity.py::test_versioned_catalog_has_registry_id_order_and_activation_parity` |
| PDF e planilhas finais | Exportar, linhas 2–5 | `tests/server/test_deliverable_exports.py::test_server_generates_pdf_and_three_real_xlsx_deliverables`; `::test_pdf_callout_is_a_downloadable_annotation_even_on_rotated_page` |
| fotos gerenciadas | Exportar, linhas 7–10 | `tests/integration/test_project_portability.py::test_export_import_preserves_ids_decisions_and_repairs_missing_photo` |
| tema, docks e geometria da janela | Janela, linhas 1–3 | `tests/integration/test_window.py::test_theme_switch_preserves_project_pdf_callout_zoom_selection_and_wrap_toggles`; `::test_floating_panel_has_window_controls_and_can_be_reopened` |
| coordenação global, progresso e cancelamento | Projeto linha 12, Exportar linha 6 e Janela linha 5 | `tests/integration/test_mvp_workflow.py::test_cancelled_analysis_releases_shared_coordinator`; `tests/integration/test_portability_panel.py::test_each_action_downloads_the_server_compiled_file`; `tests/unit/test_operation_coordinator.py::test_conflict_and_reentry_are_refused_immediately_with_friendly_message` |

## Auditoria dos pontos críticos de caracterização

O escopo da Etapa 0 permite adicionar testes apenas quando um comportamento crítico ainda não estiver
coberto. A inspeção dos testes e o gate inicial confirmaram cobertura específica:

| Ponto crítico | Caracterização encontrada | Conclusão da Etapa 0 |
|---|---|---|
| ordem de folhas | E2E de reordenação e reabertura; integração de ordem intercalada entre PDFs | coberto; nenhum teste novo necessário |
| PDFs protegidos | senhas distintas, reuso em memória, ausência em artefatos, três tentativas e cancelamento parcial | coberto; nenhum teste novo necessário |
| cancelamento | análise cancelada/retomada sem duplicação, rollback de conformidade, cancelamento cooperativo de portabilidade e liberação do coordenador | coberto; nenhum teste novo necessário |
| regras | paridade de IDs/ordem/ativação do seed, validação semântica, import/export e persistência após restart | coberto; nenhum teste novo necessário |
| portabilidade | preflight puro, confirmação, fingerprint obsoleto, round trip, corrupção, degradação, backup/restore, journals e crashes | coberto; nenhum teste novo necessário |

Como não foi identificada lacuna nesses comportamentos, a Etapa 0 não altera testes, lógica nem
dependências de execução. As novas lacunas introduzidas pela fronteira HTTP — autenticação, DTOs,
streaming, idempotência, jobs e processos separados — pertencem explicitamente às etapas posteriores.
