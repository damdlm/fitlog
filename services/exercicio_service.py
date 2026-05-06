@staticmethod
    def update_exercicio_usuario(exercicio_usuario_id, user_id=None, **kwargs):
        """
        Atualiza um exercício customizado do usuário
        """
        try:
            exercicio = ExercicioUsuario.query.filter(
                ExercicioUsuario.id == exercicio_usuario_id,
                ExercicioUsuario.user_id == (user_id or BaseService.get_current_user_id())
            ).first()
            
            if not exercicio:
                logger.warning(f"Exercício {exercicio_usuario_id} não encontrado")
                return None
            
            for key, value in kwargs.items():
                if hasattr(exercicio, key):
                    setattr(exercicio, key, value)
            
            db.session.commit()
            logger.info(f"Exercício {exercicio_usuario_id} atualizado")
            return exercicio
            
        except Exception as e:
            BaseService.handle_error(e, f"Erro ao atualizar exercício usuário")
            return None
    
    @staticmethod
    def update_exercicio_customizado(exercicio_custom_id, user_id=None, **kwargs):